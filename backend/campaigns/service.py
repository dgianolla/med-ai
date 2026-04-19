"""
Serviço de campanhas ativas da clínica.

Lê arquivos .md em backend/campaigns/, parseia frontmatter estruturado
(incluindo listas) e aplica `CampaignSchema` (validação estrutural) +
`lint` (warnings de vazamento comportamental).

Regra operacional: campanha é "disponível" hoje se:
  1. Arquivo presente no diretório;
  2. status == "active";
  3. valid_from/valid_until (quando definidos) cobrem a data atual.

Para pausar: mude `status: paused` ou remova o arquivo.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

from campaigns.schema import (
    CampaignSchema,
    CampaignSchemaError,
    build_schema,
    lint,
)

logger = logging.getLogger(__name__)

CAMPAIGNS_DIR = Path(__file__).parent

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_INLINE_LIST_RE = re.compile(r"^\[(.*)\]$")


class Campaign:
    """Uma campanha carregada de um arquivo .md.

    Wrapper sobre `CampaignSchema` que preserva aliases legados usados pelo
    `CampaignAgent` e pela triagem (`nome`, `especialidade`, `valor`, `raw`).
    """

    def __init__(self, schema: CampaignSchema, raw: str):
        self.schema = schema
        self.raw = raw  # frontmatter + corpo originais (mantido para debug/trace)

    # ---- aliases legados ------------------------------------------------
    @property
    def slug(self) -> str:
        return self.schema.slug

    @property
    def nome(self) -> str:
        return self.schema.campaign_name

    @property
    def campaign_id(self) -> str:
        return self.schema.campaign_id

    @property
    def especialidade(self) -> Optional[str]:
        return self.schema.especialidade

    @property
    def valor(self) -> Optional[str]:
        return self.schema.offer_anchor

    @property
    def body(self) -> str:
        return self.schema.body

    # ---- resumo para o índice da triage --------------------------------
    def summary(self) -> str:
        """Primeira linha útil do corpo."""
        for line in self.schema.body.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            return s[:140]
        return ""

    def index_entry(self) -> str:
        """Linha única descrevendo a campanha para o índice da triagem."""
        parts = [f'"{self.nome}"']
        meta = []
        if self.especialidade:
            meta.append(f"especialidade: {self.especialidade}")
        if self.valor:
            meta.append(self.valor)
        if meta:
            parts.append(" / ".join(meta))
        summary = self.summary()
        if summary:
            parts.append(summary)
        return " — ".join(parts)


# ------------------------------------------------------------------
# Parser de frontmatter (suporta listas)
# ------------------------------------------------------------------

def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    """Parser mínimo que aceita:

    - `key: value` simples
    - `key: [a, b, c]` inline list
    - `key:` seguido de linhas `  - item` (lista indentada)
    - linhas vazias e comentários `# ...` ignoradas
    """
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw

    fm_block, body = match.group(1), match.group(2)
    fm: dict = {}

    lines = fm_block.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if ":" not in stripped:
            i += 1
            continue

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if value == "":
            # Pode ser bloco-lista com bullets nas linhas seguintes.
            items: list[str] = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                nxt_stripped = nxt.strip()
                if not nxt_stripped:
                    j += 1
                    continue
                if nxt_stripped.startswith("-"):
                    items.append(nxt_stripped.lstrip("-").strip().strip('"').strip("'"))
                    j += 1
                    continue
                break
            if items:
                fm[key] = items
                i = j
                continue
            fm[key] = ""
            i += 1
            continue

        inline = _INLINE_LIST_RE.match(value)
        if inline:
            raw_items = inline.group(1).split(",")
            fm[key] = [item.strip().strip('"').strip("'") for item in raw_items if item.strip()]
        else:
            fm[key] = value

        i += 1

    return fm, body


# ------------------------------------------------------------------
# Serviço
# ------------------------------------------------------------------

class CampaignService:
    """Carrega e serve campanhas ativas com cache em memória."""

    def __init__(self, today_provider=None):
        self._cache_all: dict[str, Campaign] = {}  # keyed by campaign_name (case-preserved)
        self._loaded = False
        # permite teste injetar data; default = date.today na hora do load
        self._today_provider = today_provider or date.today

    # --- carga -----------------------------------------------------------
    def _load_all(self) -> None:
        if self._loaded:
            return

        self._cache_all.clear()
        for md_file in sorted(CAMPAIGNS_DIR.glob("*.md")):
            if md_file.name.startswith("_"):
                continue
            try:
                raw = md_file.read_text(encoding="utf-8")
                frontmatter, body = _parse_frontmatter(raw)

                try:
                    schema = build_schema(slug=md_file.stem, frontmatter=frontmatter, body=body)
                except CampaignSchemaError as e:
                    logger.error(
                        "Campanha ignorada (schema inválido): %s | file=%s",
                        e, md_file.name,
                    )
                    continue

                warnings = lint(schema)
                for w in warnings:
                    logger.warning("Campanha %s: %s", md_file.name, w)

                campaign = Campaign(schema=schema, raw=raw)

                if schema.campaign_name in self._cache_all:
                    logger.error(
                        "Campanha duplicada ignorada: nome já existe | file=%s | nome=%s",
                        md_file.name, schema.campaign_name,
                    )
                    continue

                self._cache_all[schema.campaign_name] = campaign
                logger.info(
                    "Campanha carregada: %s | file=%s | id=%s | status=%s | especialidade=%s | offer=%s",
                    schema.campaign_name, md_file.name, schema.campaign_id, schema.status,
                    schema.especialidade, schema.offer_anchor,
                )
            except Exception as e:  # noqa: BLE001
                logger.error("Erro ao carregar campanha %s: %s", md_file.name, e)

        self._loaded = True

    # --- API pública -----------------------------------------------------
    def list_all(self) -> list[Campaign]:
        """Lista campanhas disponíveis hoje (status active + dentro da janela)."""
        self._load_all()
        today = self._today_provider()
        return [c for c in self._cache_all.values() if c.schema.is_active_on(today)]

    def list_loaded(self) -> list[Campaign]:
        """Lista todas as campanhas carregadas (sem filtrar por ciclo de vida).

        Útil para debug/diagnóstico.
        """
        self._load_all()
        return list(self._cache_all.values())

    def get(self, nome: str) -> Optional[Campaign]:
        """Busca campanha por nome exato (case-insensitive).

        Retorna None se a campanha não existe OU se não estiver disponível hoje
        (paused / fora da janela valid_from-valid_until). Isto casa com o
        comportamento esperado pelo `CampaignAgent`: se a campanha saiu do ar,
        cai no fallback de "campanha não encontrada".
        """
        self._load_all()
        target = nome.strip().lower()
        today = self._today_provider()
        for c in self._cache_all.values():
            if c.schema.campaign_name.lower() == target:
                return c if c.schema.is_active_on(today) else None
        return None

    def index_text(self) -> str:
        """Texto pronto para injetar no system prompt da triagem.

        Inclui só campanhas disponíveis hoje.
        """
        campaigns = self.list_all()
        if not campaigns:
            return ""

        lines = [
            "## CAMPANHAS ATIVAS",
            "",
            "As campanhas abaixo estão no ar. Se a mensagem do paciente bater",
            "com o tema de uma delas, roteie para o agente `campaign` passando",
            "o nome exato da campanha. Se não bater com nenhuma, siga o fluxo",
            "normal (commercial, weight_loss, exams, etc.).",
            "",
        ]
        for c in campaigns:
            lines.append(f"- {c.index_entry()}")
        return "\n".join(lines)

    def reload(self) -> None:
        """Força reload do diretório. Útil em dev."""
        self._loaded = False
        self._cache_all.clear()
        self._load_all()


_service: Optional[CampaignService] = None


def get_campaign_service() -> CampaignService:
    global _service
    if _service is None:
        _service = CampaignService()
    return _service
