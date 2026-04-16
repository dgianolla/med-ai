import json
import logging
import re
from typing import Any

from anthropic import AsyncAnthropic
from postgrest.exceptions import APIError

from config import get_settings
from db.client import get_supabase
from db.models import IncomingMessage
from integrations.scheduling_api import cancel_appointment, confirm_appointment

logger = logging.getLogger(__name__)

CONFIRMATION_INTENTS = {"sim", "nao", "fora_de_contexto"}

_CLINIC_WHATSAPP = "(15) 99695-0709"


def _fallback_classify(text: str) -> str:
    text = (text or "").lower().strip()

    sim_patterns = [
        r"\b(sim|confirmo|confirmado|confirmada|confirmar|ok|okay|certo|pode ser|vou sim|estarei a[ií]|comparecerei)\b",
    ]
    nao_patterns = [
        r"\b(n[aã]o|nao vou|n[aã]o consigo|n[aã]o poderei|n[aã]o posso|cancelar|cancela|cancelo|desmarcar|desmarca)\b",
    ]

    if any(re.search(p, text) for p in nao_patterns):
        return "nao"
    if any(re.search(p, text) for p in sim_patterns):
        return "sim"
    return "fora_de_contexto"


async def _classify_confirmation_intent(text: str) -> str:
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    system = (
        "Você classifica respostas curtas de pacientes a uma mensagem de confirmação de consulta. "
        "Sua única missão é retornar o rótulo. Responda APENAS JSON válido com a chave intent. "
        "Rótulos permitidos: sim, nao, fora_de_contexto. "
        "- sim: o paciente confirma que vai comparecer (ex.: 'sim', 'confirmo', 'ok', 'estarei aí'). "
        "- nao: o paciente diz que não vai comparecer, quer cancelar ou desmarcar. "
        "- fora_de_contexto: qualquer outra coisa — dúvidas, pedidos de remarcação, saudações, "
        "mensagens ambíguas, reclamações, áudios/imagens ou assuntos não relacionados."
    )

    user_prompt = (
        "Classifique a mensagem abaixo.\n"
        f"Mensagem: {text}\n\n"
        'Formato obrigatório: {"intent":"sim|nao|fora_de_contexto"}'
    )

    response = await client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=60,
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

        try:
            res = await (
                db.table("schedule_confirmations")
                .select("id, session_id, patient_phone, patient_name, status, appointment_id")
                .eq(column, value)
                .in_("status", ["pending", "sent"])
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
        except APIError as e:
            if e.message == "Could not find the table 'public.schedule_confirmations' in the schema cache":
                logger.error(
                    "Tabela schedule_confirmations ausente no banco/cache do PostgREST. "
                    "O fluxo de confirmação será ignorado até a migration ser aplicada."
                )
                return None
            raise

        if res.data:
            logger.info(
                "[CONFIRMATION] Match encontrado | lookup=%s | value=%s | confirmation_id=%s | appointment_id=%s | status=%s",
                column,
                value,
                res.data[0]["id"],
                res.data[0]["appointment_id"],
                res.data[0]["status"],
            )
            return res.data[0]

        logger.info(
            "[CONFIRMATION] Nenhum match | lookup=%s | value=%s",
            column,
            value,
        )

    return None


def _build_out_of_context_reply(patient_name: str | None) -> str:
    name = (patient_name or "").strip() or "tudo bem"
    return (
        f"Olá, {name}! 😊\n\n"
        "Este canal é exclusivo para confirmação de consultas e não conseguimos responder sua mensagem por aqui.\n\n"
        "Para dúvidas, remarcações ou outros assuntos, por favor entre em contato pelo WhatsApp:\n"
        f"📲 {_CLINIC_WHATSAPP}\n\n"
        "Agradecemos a compreensão!"
    )


async def handle_confirmation(message: IncomingMessage) -> dict[str, Any] | None:
    """
    Processa respostas às mensagens de confirmação disparadas pelo painel.
    Retorna None quando a mensagem não pertence a uma confirmação ativa.
    """
    active = await _find_active_confirmation(message)
    if not active:
        return None

    appointment_id = active.get("appointment_id")
    patient_name = active.get("patient_name")

    try:
        intent = await _classify_confirmation_intent(message.text)
    except Exception as e:
        logger.warning("Falha ao classificar confirmação com LLM, usando fallback: %s", e)
        intent = _fallback_classify(message.text)

    if intent == "sim":
        try:
            await confirm_appointment(appointment_id)
            logger.info("[CONFIRMATION] api-vizi confirmar OK | appointment_id=%s", appointment_id)
        except Exception as e:
            logger.error(
                "[CONFIRMATION] Falha ao chamar PUT /agendamentos/%s/confirmar: %s",
                appointment_id, e, exc_info=True,
            )
        new_status = "confirmed"
        reply = (
            f"Perfeito, {patient_name or 'tudo certo'}! ✅\n"
            "Sua consulta está confirmada. Te aguardamos no horário agendado."
        )

    elif intent == "nao":
        try:
            await cancel_appointment(appointment_id, reason="Paciente não confirmou a consulta via WhatsApp")
            logger.info("[CONFIRMATION] api-vizi cancelar OK | appointment_id=%s", appointment_id)
        except Exception as e:
            logger.error(
                "[CONFIRMATION] Falha ao chamar PUT /agendamentos/%s/cancelar: %s",
                appointment_id, e, exc_info=True,
            )
        new_status = "canceled"
        reply = (
            f"Tudo certo, {patient_name or ''}. Registramos que você não poderá comparecer.\n\n"
            f"Se quiser remarcar, fale com a clínica pelo WhatsApp: 📲 {_CLINIC_WHATSAPP}"
        )

    else:  # fora_de_contexto
        new_status = "sent"  # não finaliza — paciente pode responder SIM/NAO depois
        reply = _build_out_of_context_reply(patient_name)

    if new_status != active.get("status"):
        try:
            db = await get_supabase()
            await db.table("schedule_confirmations").update({"status": new_status}).eq("id", active["id"]).execute()
        except Exception as e:
            logger.error("Erro ao atualizar status da confirmação %s: %s", active["id"], e)

    logger.info(
        "[CONFIRMATION] processada | appointment_id=%s | phone=%s | intent=%s | status=%s | text=%s",
        appointment_id,
        active.get("patient_phone"),
        intent,
        new_status,
        message.text[:120],
    )

    return {
        "handled": True,
        "intent": intent,
        "status": new_status,
        "reply": reply,
        "is_final": new_status in {"confirmed", "canceled"},
    }
