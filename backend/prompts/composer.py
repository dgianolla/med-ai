"""
Composer do system prompt em camadas (L1..L5 + REF).

Monta o system prompt final concatenando camadas nomeadas, precedido da
meta-regra de precedência, para que o modelo saiba qual camada vence em
caso de conflito e possa auto-reportar conflitos via marcação [[conflict: ...]].

Layout final:

  [META-REGRA]
  <<<BEGIN L1 ...>>>  safety
  <<<BEGIN L2 ...>>>  core identity do agente
  <<<BEGIN L3 ...>>>  global business rules
  <<<BEGIN REF ...>>> catálogo de campanhas ativas (referência, não regra)
  <<<BEGIN L4 ...>>>  contexto da campanha específica do lead (se houver)
  <<<BEGIN L5 ...>>>  metadata da sessão (fatos, não regra)

A função `compose_agent_system` é agnóstica ao tipo de agente — serve tanto
para triage quanto para scheduling, campaign, etc. O composer antigo
`compose_campaign_system` continua disponível como alias para compat.
"""

from __future__ import annotations

import re
from typing import Optional


# ------------------------------------------------------------------
# Meta-regra
# ------------------------------------------------------------------

META_RULE = """\
# HIERARQUIA DE CAMADAS (META-REGRA)

Este prompt está organizado em camadas, da maior para a menor prioridade:

- L1 — SAFETY / CLINICAL GUARDRAILS
- L2 — CORE IDENTITY
- L3 — GLOBAL BUSINESS RULES
- REF — CATÁLOGO DE CAMPANHAS ATIVAS (REFERÊNCIA)
- L4 — ACTIVE CAMPAIGN CONTEXT
- L5 — SESSION METADATA

Regras de resolução de conflito:

1. Em caso de conflito, a camada de **menor número vence**. L1 > L2 > L3 > L4 > L5.
2. L4 (campanha) NUNCA sobrescreve L1, L2 ou L3. Se a campanha pedir algo que
   contradiga L1/L2/L3, **siga L1/L2/L3** e ignore a instrução conflitante da campanha.
3. REF é **referência informacional**, não regra — apenas lista quais campanhas existem
   e seus dados de catálogo. Use para reconhecer quando o paciente mencionar uma
   campanha que não é a que você está atendendo agora. Se precisar executar o fluxo
   de outra campanha, use o mecanismo normal de handoff (agente `campaign`).
4. L5 (metadata da sessão) é apenas informação factual sobre o paciente. Não contém regra.
5. Tools disponíveis (`list_active_campaigns`, `get_campaign_details`) permitem consultar
   detalhes dinâmicos de qualquer campanha ativa quando REF não for suficiente.
6. Se você identificar conflito real entre camadas, inclua no **início** da sua resposta
   a marcação técnica:
       [[conflict: Lx vs Ly | resumo curto do conflito]]
   Essa marcação será removida automaticamente antes de enviar ao paciente. Use-a apenas
   quando houver conflito real — nunca por hábito.

Os blocos de cada camada são delimitados por marcadores `<<<BEGIN Lx ...>>>` e `<<<END Lx ...>>>`.
"""


_LAYER_ORDER = (
    ("L1", "SAFETY / CLINICAL GUARDRAILS"),
    ("L2", "CORE IDENTITY"),
    ("L3", "GLOBAL BUSINESS RULES"),
    ("REF", "CATÁLOGO DE CAMPANHAS ATIVAS (REFERÊNCIA)"),
    ("L4", "ACTIVE CAMPAIGN CONTEXT"),
    ("L5", "SESSION METADATA"),
)


def _wrap_layer(code: str, title: str, content: str) -> str:
    return (
        f"<<<BEGIN {code} — {title}>>>\n"
        f"{content.strip()}\n"
        f"<<<END {code} — {title}>>>"
    )


# ------------------------------------------------------------------
# Composer genérico
# ------------------------------------------------------------------

def compose_agent_system(
    *,
    safety: str = "",
    core_identity: str = "",
    business_rules: str = "",
    campaigns_index: str = "",
    campaign_block: str = "",
    session_metadata: str = "",
) -> tuple[str, dict]:
    """Compõe system prompt em camadas para qualquer agente.

    Cada camada vazia é omitida do prompt final (não gera bloco).
    Retorna tupla (system_prompt, trace). Trace contém `layers_present` e
    `layers_total_chars` para diagnóstico.
    """
    layer_contents = {
        "L1": safety,
        "L2": core_identity,
        "L3": business_rules,
        "REF": campaigns_index,
        "L4": campaign_block,
        "L5": session_metadata,
    }

    parts: list[str] = [META_RULE]
    layers_present: list[str] = []
    for code, title in _LAYER_ORDER:
        content = (layer_contents.get(code) or "").strip()
        if not content:
            continue
        parts.append(_wrap_layer(code, title, content))
        layers_present.append(code)

    system = "\n\n".join(parts)
    trace = {
        "layers_present": layers_present,
        "layers_total_chars": {
            code: len((layer_contents.get(code) or "").strip())
            for code, _ in _LAYER_ORDER
        },
    }
    return system, trace


# Alias backward-compat — a primeira implementação só era usada pelo CampaignAgent.
compose_campaign_system = compose_agent_system


# ------------------------------------------------------------------
# Formatters
# ------------------------------------------------------------------

def format_campaign_block(campaign) -> str:
    """Serializa uma campanha (Campaign/CampaignSchema) em um bloco L4 estruturado.

    O header é machine-readable (chave: valor). O corpo `.body` do .md vai
    abaixo como conteúdo operacional (fluxo, FAQ, escalonamento).
    """
    schema = campaign.schema  # Campaign.schema

    header_lines = [
        "## Metadados da campanha",
        f"- campaign_id: {schema.campaign_id}",
        f"- campaign_name: {schema.campaign_name}",
        f"- status: {schema.status}",
        f"- especialidade: {schema.especialidade or '—'}",
        f"- offer_anchor: {schema.offer_anchor or '—'}",
        f"- handoff_target: {schema.handoff_target}",
    ]
    if schema.valid_from or schema.valid_until:
        header_lines.append(
            f"- janela: {schema.valid_from or '∅'} → {schema.valid_until or '∅'}"
        )

    allowed = "\n".join(f"- {p}" for p in schema.allowed_promises) or "(nenhuma listada)"
    forbidden = "\n".join(f"- {p}" for p in schema.forbidden_promises) or "(nenhuma listada)"

    return (
        "\n".join(header_lines)
        + "\n\n## Promessas permitidas nesta campanha\n"
        + allowed
        + "\n\n## Promessas proibidas nesta campanha\n"
        + forbidden
        + "\n\n## Conteúdo operacional da campanha\n"
        + schema.body.strip()
    )


def format_campaigns_index(service) -> str:
    """Serializa o catálogo de campanhas ATIVAS como REF.

    Usado por todos os agentes para terem ciência das campanhas disponíveis,
    não apenas a triagem. Se não há campanhas ativas, retorna "".
    """
    campaigns = service.list_all()
    if not campaigns:
        return ""

    lines = [
        "Estas são as campanhas comerciais ativas no momento. Use a lista para",
        "reconhecer quando o paciente mencionar uma dessas ofertas. Se precisar",
        "executar o fluxo de uma campanha específica, encaminhe via handoff",
        "para o agente `campaign`. Para detalhes adicionais, use a tool",
        "`get_campaign_details(campaign_id)`.",
        "",
    ]
    for c in campaigns:
        schema = c.schema
        parts = [f"- **{schema.campaign_name}** (id: `{schema.campaign_id}`)"]
        meta = []
        if schema.especialidade:
            meta.append(f"especialidade: {schema.especialidade}")
        if schema.offer_anchor:
            meta.append(f"oferta: {schema.offer_anchor}")
        if meta:
            parts.append(" / ".join(meta))
        summary = c.summary()
        if summary:
            parts.append(summary)
        lines.append(" — ".join(parts))
    return "\n".join(lines)


def format_session_state(
    ctx,
    *,
    extra_facts: Optional[list[str]] = None,
) -> str:
    """Serializa metadata/handoff/knowledge em um bloco L5.

    - Inclui nome do paciente, motivo do handoff, metadata coletada, flow.
    - Aceita `extra_facts`: lista de strings extras (ex.: snapshot de pagamento
      da knowledge base, contexto de combo, etc.) que o agente específico queira
      injetar em L5.
    - Retorna "" se não há nada — permitindo omitir a camada inteira.
    """
    lines: list[str] = []

    if getattr(ctx, "handoff_payload", None):
        payload = ctx.handoff_payload
        if getattr(payload, "patient_name", None):
            lines.append(f"- paciente: {payload.patient_name}")
        if getattr(payload, "reason", None):
            lines.append(f"- motivo do encaminhamento: {payload.reason}")
        if getattr(payload, "specialty_needed", None):
            lines.append(f"- especialidade alvo: {payload.specialty_needed}")
        if getattr(payload, "combo_id", None):
            lines.append(f"- combo em curso: {payload.combo_id}")
        context = getattr(payload, "context", None) or {}
        for key in ("convenio", "specialty", "scheduled_date", "scheduled_time",
                    "appointment_id", "previous_agent", "lead_source",
                    "campaign_name", "combo_name"):
            if context.get(key):
                lines.append(f"- {key}: {context[key]}")

    if getattr(ctx, "patient_metadata", None):
        for key, value in ctx.patient_metadata.items():
            if key in {"name", "convenio", "specialty", "interest"} and value:
                lines.append(f"- metadata.{key}: {value}")

    if getattr(ctx, "flow_type", None) or getattr(ctx, "flow_stage", None):
        lines.append(f"- flow: {ctx.flow_type or '—'} / {ctx.flow_stage or '—'}")

    if extra_facts:
        lines.extend(f"- {f}" for f in extra_facts if f)

    if not lines:
        return ""

    # Dedup preservando ordem
    seen = set()
    unique_lines = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        unique_lines.append(line)

    return "## Fatos da sessão\n" + "\n".join(unique_lines)


# Alias backward-compat
format_session_metadata = format_session_state


# ------------------------------------------------------------------
# Conflict tag extractor
# ------------------------------------------------------------------

_CONFLICT_TAG_RE = re.compile(r"\[\[\s*conflict\s*:(.*?)\]\]", re.IGNORECASE | re.DOTALL)


def extract_and_strip_conflicts(reply: Optional[str]) -> tuple[str, list[str]]:
    """Extrai marcações [[conflict: ...]] da resposta e devolve reply limpo."""
    if not reply:
        return "", []

    conflicts = [m.group(1).strip() for m in _CONFLICT_TAG_RE.finditer(reply)]
    clean = _CONFLICT_TAG_RE.sub("", reply).strip()
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean, conflicts


# ------------------------------------------------------------------
# Helper de alto nível para agentes
# ------------------------------------------------------------------

def build_agent_system(
    *,
    agent_name: str,
    ctx,
    extra_facts: Optional[list[str]] = None,
    extra_identity_suffix: str = "",
) -> tuple[str, dict]:
    """Helper conveniente para agentes: carrega L1/L2/L3/REF/L4/L5 automaticamente.

    - `agent_name`: nome do prompt a carregar (prompts/{agent_name}.md) como L2.
    - `ctx`: SessionContext. Se ctx.handoff_payload.context["campaign_name"] existir
      e apontar para uma campanha ativa, L4 é injetado.
    - `extra_facts`: fatos adicionais para L5 (ex.: knowledge snapshot).
    - `extra_identity_suffix`: texto opcional anexado a L2 (usado por agentes que
      injetam knowledge específico do protocolo, ex.: política de exames).

    Retorna (system_prompt, trace_dict). O trace inclui também:
      - `agent`: nome do agente
      - `campaign_id`: id da campanha ativa (ou None)
    """
    # imports tardios para evitar ciclo com prompt_loader/service
    from agents.prompt_loader import load_prompt
    from campaigns.service import get_campaign_service

    core_identity = load_prompt(agent_name)
    if extra_identity_suffix:
        core_identity = f"{core_identity.rstrip()}\n\n{extra_identity_suffix.strip()}"

    safety = load_prompt("_safety")
    business_rules = load_prompt("_business_rules")

    service = get_campaign_service()
    campaigns_index = format_campaigns_index(service)

    campaign_block = ""
    campaign_id: Optional[str] = None
    if getattr(ctx, "handoff_payload", None) and ctx.handoff_payload.context:
        campaign_name = ctx.handoff_payload.context.get("campaign_name")
        if campaign_name:
            campaign = service.get(campaign_name)
            if campaign:
                campaign_block = format_campaign_block(campaign)
                campaign_id = campaign.campaign_id

    session_metadata = format_session_state(ctx, extra_facts=extra_facts)

    system, trace = compose_agent_system(
        safety=safety,
        core_identity=core_identity,
        business_rules=business_rules,
        campaigns_index=campaigns_index,
        campaign_block=campaign_block,
        session_metadata=session_metadata,
    )
    trace["agent"] = agent_name
    trace["campaign_id"] = campaign_id
    return system, trace
