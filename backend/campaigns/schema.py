"""
Schema de campanha e linter estático.

Representa o contrato da camada L4 (Active Campaign Context):
- Frontmatter validado estruturalmente (campos, tipos, datas, status).
- Corpo livre em Markdown, mas com detecção de "vazamento comportamental"
  (instruções que pertenceriam a L2/L3, como tom, identidade, formato).

A função `lint` nunca falha por conteúdo de corpo — ela retorna warnings que
o loader registra. Erros estruturais (campo obrigatório ausente, status/data
inválidos) fazem o loader pular a campanha.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


VALID_STATUSES = {"active", "paused", "draft"}
VALID_HANDOFF_TARGETS = {"scheduling", "commercial", "human", "none"}

# Headings de `## ...` que sinalizam instrução comportamental indevida
# dentro de um campaign file (pertenceriam a L2/L3, não L4).
_BEHAVIORAL_HEADING_RE = re.compile(
    r"^\s*##+\s*(tom|identidade|personalidade|persona|formato|guardrails?)\b",
    re.IGNORECASE | re.MULTILINE,
)

# Padrões inline que tipicamente são regra de agente, não conteúdo de campanha.
_BEHAVIORAL_INLINE_PATTERNS = [
    (re.compile(r"\bvoc[êe]\s+[ée]\s+a\s+LIA\b", re.IGNORECASE), "redefine identidade do agente"),
    (re.compile(r"\bignore\b.*(prompt|system|regra\s+global)", re.IGNORECASE), "pede para ignorar regras globais"),
    (re.compile(r"\bsobrescreva\b", re.IGNORECASE), "pede para sobrescrever comportamento"),
]


@dataclass
class CampaignSchema:
    """Shape canônico de uma campanha carregada."""

    # Obrigatórios
    campaign_id: str
    campaign_name: str

    # Ciclo de vida
    status: str = "active"
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    priority: int = 50

    # Oferta / roteamento
    source: Optional[str] = None
    especialidade: Optional[str] = None
    offer_anchor: Optional[str] = None
    handoff_target: str = "scheduling"

    # Promessas
    allowed_promises: list[str] = field(default_factory=list)
    forbidden_promises: list[str] = field(default_factory=list)

    # Corpo em Markdown (fluxo, FAQ, escalonamento, etc.)
    body: str = ""

    # Origem
    slug: str = ""

    # --------------------------------------------------------------
    # Helpers de ciclo de vida
    # --------------------------------------------------------------

    def is_active_on(self, today: date) -> bool:
        """Campanha disponível na data `today`?"""
        if self.status != "active":
            return False
        if self.valid_from and today < self.valid_from:
            return False
        if self.valid_until and today > self.valid_until:
            return False
        return True


# ------------------------------------------------------------------
# Parsing / coerção
# ------------------------------------------------------------------

class CampaignSchemaError(ValueError):
    """Erro estrutural — campanha não pode ser carregada."""


def _coerce_date(raw: str, field_name: str) -> Optional[date]:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as e:
        raise CampaignSchemaError(f"{field_name} inválido (esperado ISO yyyy-mm-dd): {raw}") from e


def _coerce_int(raw: str, field_name: str, default: int) -> int:
    raw = (raw or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise CampaignSchemaError(f"{field_name} inválido (esperado inteiro): {raw}") from e


def _coerce_list(raw) -> list[str]:
    """Aceita list (do parser), string vazia, ou string única como fallback."""
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [str(raw).strip()]


def build_schema(*, slug: str, frontmatter: dict, body: str) -> CampaignSchema:
    """Constrói `CampaignSchema` validado a partir do frontmatter cru.

    Aceita aliases legados: `nome` → campaign_name, `valor` → offer_anchor.
    """
    name = (frontmatter.get("campaign_name") or frontmatter.get("nome") or "").strip()
    if not name:
        raise CampaignSchemaError("campaign_name (ou nome) é obrigatório")

    campaign_id = (frontmatter.get("campaign_id") or slug).strip()
    if not campaign_id:
        raise CampaignSchemaError("campaign_id vazio e slug indisponível")

    status = (frontmatter.get("status") or "active").strip().lower()
    if status not in VALID_STATUSES:
        raise CampaignSchemaError(f"status inválido: {status} (esperado: {sorted(VALID_STATUSES)})")

    handoff_target = (frontmatter.get("handoff_target") or "scheduling").strip().lower()
    if handoff_target not in VALID_HANDOFF_TARGETS:
        raise CampaignSchemaError(
            f"handoff_target inválido: {handoff_target} (esperado: {sorted(VALID_HANDOFF_TARGETS)})"
        )

    return CampaignSchema(
        campaign_id=campaign_id,
        campaign_name=name,
        status=status,
        valid_from=_coerce_date(frontmatter.get("valid_from", ""), "valid_from"),
        valid_until=_coerce_date(frontmatter.get("valid_until", ""), "valid_until"),
        priority=_coerce_int(frontmatter.get("priority", ""), "priority", default=50),
        source=(frontmatter.get("source") or "").strip() or None,
        especialidade=(frontmatter.get("especialidade") or "").strip() or None,
        offer_anchor=(frontmatter.get("offer_anchor") or frontmatter.get("valor") or "").strip() or None,
        handoff_target=handoff_target,
        allowed_promises=_coerce_list(frontmatter.get("allowed_promises")),
        forbidden_promises=_coerce_list(frontmatter.get("forbidden_promises")),
        body=body,
        slug=slug,
    )


# ------------------------------------------------------------------
# Linter (warnings não-bloqueantes)
# ------------------------------------------------------------------

def lint(schema: CampaignSchema) -> list[str]:
    """Retorna lista de warnings. Lista vazia = campanha limpa.

    Os warnings são registrados pelo loader e servem como sinal operacional;
    não impedem o carregamento.
    """
    warnings: list[str] = []

    if schema.valid_from and schema.valid_until and schema.valid_until < schema.valid_from:
        warnings.append("valid_until anterior a valid_from")

    if schema.priority < 0 or schema.priority > 100:
        warnings.append(f"priority fora do intervalo recomendado [0..100]: {schema.priority}")

    # Vazamento comportamental no corpo
    for match in _BEHAVIORAL_HEADING_RE.finditer(schema.body):
        warnings.append(
            f"seção com cara de regra global/identidade em campaign body: {match.group(0).strip()!r}"
        )

    for pattern, reason in _BEHAVIORAL_INLINE_PATTERNS:
        if pattern.search(schema.body):
            warnings.append(f"possível vazamento comportamental no corpo: {reason}")

    # Integridade mínima do corpo
    if len(schema.body.strip()) < 40:
        warnings.append("corpo da campanha muito curto — faltando fluxo/contexto?")

    return warnings
