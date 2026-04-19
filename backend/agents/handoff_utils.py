import re
import unicodedata

from db.models import HandoffPayload, SessionContext


# ----------------------------------------------------------------------
# Matching de frase-gatilho (agentes que decidem handoff por texto da resposta)
# ----------------------------------------------------------------------

SCHEDULING_HANDOFF_PHRASES: tuple[str, ...] = (
    "vou te encaminhar para agendamento",
    "vou te encaminhar pro agendamento",
    "vou te encaminhar para a agenda",
    "vou te encaminhar pra agenda",
    "vou te passar para agendamento",
    "vou te passar pro agendamento",
    "vou te passar para a agenda",
    "vou te levar para agendamento",
    "vou te levar pro agendamento",
    "te encaminhar para agendamento",
    "te encaminhar pro agendamento",
    "te encaminhar para a agenda",
    "agente de agendamento",
    "equipe de agendamento",
)

COMMERCIAL_HANDOFF_PHRASES: tuple[str, ...] = (
    "vou te encaminhar para o comercial",
    "vou te encaminhar pro comercial",
    "vou transferir para o comercial",
    "vou transferir pro comercial",
    "te encaminhar para o comercial",
    "te encaminhar pro comercial",
    "te passar para o comercial",
    "te passar pro comercial",
    "nosso setor comercial",
    "colega do comercial",
    "equipe comercial",
    "agente comercial",
)

HUMAN_HANDOFF_PHRASES: tuple[str, ...] = (
    "vou te encaminhar agora para nossa equipe",
    "vou te encaminhar para nossa equipe",
    "vou te passar para nossa equipe",
    "vou chamar nossa equipe",
)

DONE_PHRASES: tuple[str, ...] = (
    "ate logo",
    "ate mais",
    "obrigado por entrar em contato",
    "qualquer duvida",
    "qualquer coisa",
    "boa consulta",
    "tenha um otimo dia",
    "fico a disposicao",
    "estamos a disposicao",
)


def _normalize_text(text: str) -> str:
    """Minúsculo, sem acentos, sem pontuação, espaços colapsados."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = without_accents.lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", lowered).strip()
    return re.sub(r"\s+", " ", cleaned)


def matches_any_phrase(text: str | None, phrases: tuple[str, ...] | list[str]) -> bool:
    """True se `text` contém qualquer frase de `phrases`, ignorando acento/caixa/pontuação.

    As frases em `phrases` devem vir já normalizadas (sem acento/maiúscula) para evitar
    custo de renormalização em cada chamada. As constantes deste módulo seguem isso.
    """
    normalized = _normalize_text(text or "")
    if not normalized:
        return False
    return any(phrase in normalized for phrase in phrases)


# ----------------------------------------------------------------------
# Builders de handoff
# ----------------------------------------------------------------------


def previous_context(ctx: SessionContext) -> dict:
    if ctx.handoff_payload and ctx.handoff_payload.context:
        return dict(ctx.handoff_payload.context)
    return {}


def set_consultation_flow(ctx: SessionContext) -> None:
    ctx.flow_type = "consultation"
    ctx.flow_stage = None
    ctx.combo_id = None


def set_combo_flow(ctx: SessionContext, combo_id: str) -> None:
    ctx.flow_type = "combo"
    ctx.flow_stage = "waiting_consultation_schedule"
    ctx.combo_id = combo_id


def build_consultation_scheduling_handoff(
    ctx: SessionContext,
    *,
    patient_name: str | None,
    reason: str,
    source_agent: str,
    specialty_needed: str | None = None,
    extra_context: dict | None = None,
    invisible: bool = True,
) -> HandoffPayload:
    context = {
        "offer_type": "consultation",
        "flow_type": "consultation",
        "previous_agent": source_agent,
        **previous_context(ctx),
    }
    if invisible:
        context["invisible_handoff"] = True
    if extra_context:
        context.update(extra_context)

    return HandoffPayload(
        type="to_scheduling",
        patient_name=patient_name,
        reason=reason,
        specialty_needed=specialty_needed,
        context=context,
    )


def build_combo_scheduling_handoff(
    ctx: SessionContext,
    *,
    patient_name: str | None,
    reason: str,
    source_agent: str,
    combo: dict,
    extra_context: dict | None = None,
    invisible: bool = True,
) -> HandoffPayload:
    context = {
        "offer_type": "combo",
        "flow_type": "combo",
        "combo_id": combo["combo_id"],
        "combo_name": combo["name"],
        "collection_included": combo["collection_included"],
        "collection_schedule_required": combo["collection_schedule_required"],
        "previous_agent": source_agent,
        **previous_context(ctx),
    }
    if invisible:
        context["invisible_handoff"] = True
    if extra_context:
        context.update(extra_context)

    return HandoffPayload(
        type="to_scheduling",
        patient_name=patient_name,
        reason=reason,
        specialty_needed=combo["consultation_specialty"],
        combo_id=combo["combo_id"],
        context=context,
    )
