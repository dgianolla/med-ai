import json
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from config import get_settings
from db.models import SessionContext, HandoffPayload, AgentType

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Gerencia contextos de sessão no Upstash Redis via REST API.
    TTL padrão: 30 minutos (reset a cada mensagem).
    """

    MAX_HISTORY = 15  # máximo de mensagens no sliding window

    def __init__(self):
        settings = get_settings()
        self.base_url = settings.upstash_redis_rest_url
        self.token = settings.upstash_redis_rest_token
        self.ttl = settings.session_ttl_seconds

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _session_key(self, session_id: str) -> str:
        return f"session:{session_id}"

    async def _redis_get(self, key: str) -> Optional[str]:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{self.base_url}/get/{key}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("result")

    async def _redis_set(self, key: str, value: str, ttl: int) -> None:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{self.base_url}/set/{key}/{value}/ex/{ttl}",
                headers=self._headers(),
            )
            resp.raise_for_status()

    async def _redis_del(self, key: str) -> None:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.get(
                f"{self.base_url}/del/{key}",
                headers=self._headers(),
            )

    # ----------------------------------------------------------------
    # API pública
    # ----------------------------------------------------------------

    async def get(self, session_id: str) -> Optional[SessionContext]:
        """Carrega sessão do Redis. Retorna None se não existir."""
        raw = await self._redis_get(self._session_key(session_id))
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return SessionContext(**data)
        except Exception:
            logger.warning("Sessão corrompida no Redis: %s — descartando", session_id)
            return None

    async def create(
        self,
        session_id: str,
        patient_phone: str,
        wts_session_id: str,
        patient_name: Optional[str] = None,
    ) -> SessionContext:
        """Cria nova sessão iniciando no agente de Triagem."""
        now = datetime.now(timezone.utc)
        ctx = SessionContext(
            session_id=session_id,
            patient_phone=patient_phone,
            wts_session_id=wts_session_id,
            current_agent="triage",
            conversation_history=[],
            patient_metadata={"name": patient_name} if patient_name else None,
            created_at=now,
            last_activity_at=now,
        )
        await self.save(ctx)
        return ctx

    async def save(self, ctx: SessionContext) -> None:
        """Persiste sessão no Redis com TTL renovado."""
        ctx.last_activity_at = datetime.now(timezone.utc)
        raw = ctx.model_dump_json()
        # URL encode o valor para evitar problemas com caracteres especiais
        import urllib.parse
        encoded = urllib.parse.quote(raw, safe="")
        await self._redis_set(self._session_key(ctx.session_id), encoded, self.ttl)

    async def delete(self, session_id: str) -> None:
        """Remove sessão do Redis (quando concluída)."""
        await self._redis_del(self._session_key(session_id))

    async def get_or_create(
        self,
        patient_phone: str,
        wts_session_id: str,
        patient_name: Optional[str] = None,
    ) -> tuple[SessionContext, bool]:
        """
        Retorna (sessão, is_new).
        Cria nova sessão se não existir ou estiver expirada.
        """
        session_id = f"{patient_phone}_{int(datetime.now(timezone.utc).timestamp())}"
        # Tenta encontrar sessão ativa pelo telefone
        # Chave de índice: phone -> session_id
        phone_key = f"phone:{patient_phone}"
        existing_id = await self._redis_get(phone_key)

        if existing_id:
            ctx = await self.get(existing_id)
            if ctx:
                # Renova TTL do índice
                await self._redis_set(phone_key, existing_id, self.ttl)
                return ctx, False

        # Cria nova sessão
        ctx = await self.create(session_id, patient_phone, wts_session_id, patient_name)
        # Salva índice phone -> session_id
        async with httpx.AsyncClient(timeout=5) as client:
            await client.get(
                f"{self.base_url}/set/phone:{patient_phone}/{session_id}/ex/{self.ttl}",
                headers=self._headers(),
            )
        return ctx, True

    def append_message(self, ctx: SessionContext, role: str, content: str) -> None:
        """Adiciona mensagem ao histórico com sliding window."""
        ctx.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Mantém apenas as últimas MAX_HISTORY mensagens
        if len(ctx.conversation_history) > self.MAX_HISTORY:
            ctx.conversation_history = ctx.conversation_history[-self.MAX_HISTORY:]

    def set_agent(self, ctx: SessionContext, agent: AgentType, payload: Optional[HandoffPayload] = None) -> None:
        """Troca o agente atual e armazena o handoff payload."""
        ctx.current_agent = agent
        ctx.handoff_payload = payload

    def update_patient_metadata(self, ctx: SessionContext, updates: dict) -> None:
        """Merge de dados coletados pelo agente no metadata do paciente."""
        if ctx.patient_metadata is None:
            ctx.patient_metadata = {}
        ctx.patient_metadata.update(updates)


# Instância global
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
