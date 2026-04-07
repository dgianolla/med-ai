import logging
import httpx
from .base_client import WhatsAppClient
from config import get_settings

logger = logging.getLogger(__name__)

# Mapeamento agente → nome da etiqueta no wts.chat
AGENT_TAG_NAMES = {
    "triage":     "Triagem",
    "scheduling": "Agendamento",
    "exams":      "Exames",
    "commercial": "Comercial",
    "return":     "Retorno",
}


class WtsClient(WhatsAppClient):
    """Cliente para a API wts.chat."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        settings = get_settings()
        self.base_url = base_url or settings.wts_api_url
        self.api_key = api_key or settings.wts_api_key
        # Cache: {tag_name_lower: tag_id}
        self._tag_cache: dict[str, str] | None = None

    def _headers(self) -> dict:
        return {
            "accept": "application/json",
            "content-type": "application/*+json",
            "Authorization": f"Bearer {self.api_key}",
        }

    # ----------------------------------------------------------------
    # Mensagens
    # ----------------------------------------------------------------

    async def send_text(self, session_id: str, text: str, ref_id: str | None = None) -> str:
        payload: dict = {"text": text}
        if ref_id:
            payload["refId"] = ref_id

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.base_url}/chat/v1/session/{session_id}/message",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json().get("id", "")

    async def send_template(
        self,
        session_id: str,
        template_id: str,
        parameters: dict | None = None,
    ) -> str:
        payload: dict = {"templateId": template_id}
        if parameters:
            payload["parameters"] = parameters

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.base_url}/chat/v1/session/{session_id}/message",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json().get("id", "")

    # ----------------------------------------------------------------
    # Etiquetas
    # ----------------------------------------------------------------

    async def _load_tags(self) -> dict[str, str]:
        """Carrega todas as tags do wts.chat e faz cache {nome_lower: id}."""
        if self._tag_cache is not None:
            return self._tag_cache

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self.base_url}/core/v1/tag",
                headers={"accept": "application/json", "Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            tags = resp.json()

        self._tag_cache = {
            (t.get("name") or "").lower(): t["id"]
            for t in tags
            if t.get("id") and t.get("name")
        }
        logger.info("Tags carregadas do wts.chat: %s", list(self._tag_cache.keys()))
        return self._tag_cache

    async def apply_tag(self, session_id: str, tag_name: str) -> None:
        """Aplica etiqueta à sessão. Silencioso se a tag não existir."""
        try:
            tags = await self._load_tags()
            tag_id = tags.get(tag_name.lower())
            if not tag_id:
                logger.warning("Tag '%s' não encontrada no wts.chat", tag_name)
                return

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/v1/session/{session_id}/tag",
                    headers=self._headers(),
                    json={"tagId": tag_id},
                )
                resp.raise_for_status()
            logger.info("Tag '%s' aplicada na sessão %s", tag_name, session_id)
        except Exception as e:
            logger.warning("Erro ao aplicar tag '%s': %s", tag_name, e)

    # ----------------------------------------------------------------
    # Notas internas
    # ----------------------------------------------------------------

    async def add_note(self, session_id: str, text: str) -> None:
        """Adiciona nota interna à sessão no wts.chat."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/v1/session/{session_id}/note",
                    headers=self._headers(),
                    json={"text": text},
                )
                resp.raise_for_status()
            logger.info("Nota adicionada na sessão %s", session_id)
        except Exception as e:
            logger.warning("Erro ao adicionar nota na sessão %s: %s", session_id, e)


# Instância global reutilizável
_wts_client: WtsClient | None = None
_wts_confirmation_client: WtsClient | None = None


def get_whatsapp_client() -> WhatsAppClient:
    """Cliente padrão para os bots de atendimento."""
    global _wts_client
    if _wts_client is None:
        _wts_client = WtsClient()
    return _wts_client

def get_confirmation_whatsapp_client() -> WhatsAppClient:
    """Cliente secundário para disparo de confirmações (usa chave diferente)."""
    global _wts_confirmation_client
    if _wts_confirmation_client is None:
        settings = get_settings()
        _wts_confirmation_client = WtsClient(api_key=settings.wts_api_key_confirmation)
    return _wts_confirmation_client
