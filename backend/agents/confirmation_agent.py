import json
import logging
import re
from typing import Any

from anthropic import AsyncAnthropic

from config import get_settings
from db.client import get_supabase
from db.models import IncomingMessage

logger = logging.getLogger(__name__)

CONFIRMATION_INTENTS = {
    "confirmed",
    "canceled",
    "reschedule_requested",
    "unclear",
}


def _fallback_classify(text: str) -> str:
    text = (text or "").lower().strip()

    confirm_patterns = [
        r"\b(sim|confirmo|confirmada|confirmado|confirmar|ok|okay|certo|vou sim|estarei ai|estarei aí)\b",
    ]
    cancel_patterns = [
        r"\b(n[aã]o vou|n[aã]o consigo|n[aã]o poderei|n[aã]o posso ir|cancelar|cancela|desmarcar)\b",
    ]
    reschedule_patterns = [
        r"\b(remarcar|reagendar|outro horario|outro horário|mudar horario|mudar horário|trocar horario|trocar horário)\b",
    ]

    if any(re.search(pattern, text) for pattern in reschedule_patterns):
        return "reschedule_requested"
    if any(re.search(pattern, text) for pattern in cancel_patterns):
        return "canceled"
    if any(re.search(pattern, text) for pattern in confirm_patterns):
        return "confirmed"
    return "unclear"


async def _classify_confirmation_intent(text: str) -> str:
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    system = (
        "Você classifica respostas curtas de pacientes sobre confirmação de consulta. "
        "Responda APENAS JSON válido com a chave intent. "
        "Intenções permitidas: confirmed, canceled, reschedule_requested, unclear. "
        "Use confirmed quando o paciente claramente diz que irá comparecer. "
        "Use canceled quando ele diz que não irá, quer cancelar ou não consegue comparecer. "
        "Use reschedule_requested quando quer mudar data/horário ou remarcar. "
        "Use unclear quando houver dúvida, ambiguidade ou falta de informação."
    )

    user_prompt = (
        "Classifique a mensagem abaixo.\n"
        f"Mensagem: {text}\n\n"
        'Formato obrigatório: {"intent":"confirmed|canceled|reschedule_requested|unclear"}'
    )

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=80,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )

    reply = next((block.text for block in response.content if hasattr(block, "text")), "")
    payload = json.loads(reply)
    intent = payload.get("intent")
    if intent not in CONFIRMATION_INTENTS:
        raise ValueError(f"Intent inválida retornada pela LLM: {intent}")
    return intent


async def _find_active_confirmation(message: IncomingMessage) -> dict[str, Any] | None:
    db = await get_supabase()

    for column, value in (("session_id", message.wts_session_id), ("patient_phone", message.patient_phone)):
        if not value:
            continue

        res = await (
            db.table("schedule_confirmations")
            .select("id, session_id, patient_phone, status, appointment_id")
            .eq(column, value)
            .in_("status", ["pending", "sent"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if res.data:
            return res.data[0]

    return None


def _build_confirmation_reply(intent: str) -> tuple[str, str]:
    if intent == "confirmed":
        return (
            "confirmed",
            "Perfeito! Sua consulta está confirmada. Se surgir algum imprevisto, nos avise por aqui.",
        )

    if intent == "reschedule_requested":
        return (
            "canceled",
            "Entendido. Vou registrar que você precisa remarcar. Nossa equipe pode te ajudar com um novo horário.",
        )

    if intent == "canceled":
        return (
            "canceled",
            "Tudo certo. Vou registrar que você não poderá comparecer. Se quiser remarcar, podemos te ajudar por aqui.",
        )

    return (
        "pending",
        "Quero confirmar certinho com você: responda 'Sim' se vai comparecer ou 'Não' se não poderá vir.",
    )


async def handle_confirmation(message: IncomingMessage) -> dict[str, Any] | None:
    """
    Processa respostas às mensagens de confirmação disparadas pelo painel.
    Retorna None quando a mensagem não pertence a uma confirmação ativa.
    """
    active_confirmation = await _find_active_confirmation(message)
    if not active_confirmation:
        return None

    try:
        intent = await _classify_confirmation_intent(message.text)
    except Exception as e:
        logger.warning("Falha ao classificar confirmação com LLM, usando fallback: %s", e)
        intent = _fallback_classify(message.text)

    status, reply = _build_confirmation_reply(intent)

    try:
        db = await get_supabase()
        await db.table("schedule_confirmations").update({"status": status}).eq("id", active_confirmation["id"]).execute()
    except Exception as e:
        logger.error("Erro ao atualizar status da confirmação %s: %s", active_confirmation["id"], e)

    logger.info(
        "Confirmação processada | appointment_id=%s | phone=%s | intent=%s | status=%s | text=%s",
        active_confirmation.get("appointment_id"),
        active_confirmation.get("patient_phone"),
        intent,
        status,
        message.text[:120],
    )

    return {
        "handled": True,
        "intent": intent,
        "status": status,
        "reply": reply,
        "is_final": status in {"confirmed", "canceled"},
    }
