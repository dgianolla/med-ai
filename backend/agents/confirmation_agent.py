import json
import logging
import re
from typing import Any

from anthropic import AsyncAnthropic
from postgrest.exceptions import APIError

from config import get_settings
from db.client import get_supabase
from db.models import IncomingMessage
from integrations.helena_client import complete_session
from integrations.scheduling_api import cancel_appointment, confirm_appointment

logger = logging.getLogger(__name__)

CONFIRMATION_INTENTS = {"sim", "nao", "remarcar", "alterar", "fora_de_contexto"}

_CLINIC_WHATSAPP = "(15) 99695-0709"


def _fallback_classify(text: str) -> str:
    text = (text or "").lower().strip()

    sim_patterns = [
        r"\b(sim|confirmo|confirmado|confirmada|confirmar|ok|okay|certo|pode ser|vou sim|estarei a[ií]|comparecerei)\b",
    ]
    nao_patterns = [
        r"\b(n[aã]o|nao vou|n[aã]o consigo|n[aã]o poderei|n[aã]o posso|cancelar|cancela|cancelo)\b",
    ]
    remarcar_patterns = [
        r"\b(remarcar|remarca[cç][aã]o|reagendar|reagendamento|alterar|alteracao|alteração|trocar horario|trocar horário|outro horario|outro horário)\b",
    ]

    if any(re.search(p, text) for p in nao_patterns):
        return "nao"
    if any(re.search(p, text) for p in remarcar_patterns):
        return "remarcar"
    if any(re.search(p, text) for p in sim_patterns):
        return "sim"
    return "fora_de_contexto"


def _fallback_reply(intent: str, patient_name: str | None) -> str:
    name = (patient_name or "").strip() or "tudo bem"

    if intent == "sim":
        return (
            f"Perfeito, {name}! ✅\n"
            "Sua consulta está confirmada. Te aguardamos no horário agendado."
        )
    if intent == "nao":
        return (
            f"Tudo certo, {name}.\n\n"
            "Registramos que você não poderá comparecer.\n"
            f"Se quiser remarcar, fale com a clínica pelo WhatsApp: 📲 {_CLINIC_WHATSAPP}"
        )
    if intent in {"remarcar", "alterar"}:
        return (
            f"Sem problema, {name}.\n\n"
            "Para alterar sua consulta, fale com a clínica pelo WhatsApp:\n"
            f"📲 {_CLINIC_WHATSAPP}"
        )
    return _build_out_of_context_reply(patient_name)


def _normalize_confirmation_intent(intent: str | None) -> str:
    if intent == "remarcar":
        return "alterar"
    return intent or "fora_de_contexto"


async def _classify_confirmation_response(text: str, patient_name: str | None) -> dict[str, str]:
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    system = (
        "Você responde pacientes em um canal exclusivo de confirmação de consultas. "
        "Receberá uma resposta curta após a mensagem: SIM para confirmar, NÃO para não comparecer, "
        "REMARCAR para mudar data ou horário, ou algo fora de contexto. "
        "Sua tarefa é retornar APENAS JSON válido com as chaves intent e reply. "
        "Rótulos permitidos: sim, nao, alterar, fora_de_contexto. "
        "- sim: o paciente confirma que vai comparecer (ex.: 'sim', 'confirmo', 'ok', 'estarei aí'). "
        "- nao: o paciente diz que não vai comparecer ou quer cancelar. "
        "- alterar: o paciente quer remarcar, alterar horário/data ou reagendar. "
        "- fora_de_contexto: qualquer outra coisa — dúvidas, saudações, reclamações, "
        "áudios/imagens ou assuntos não relacionados. "
        "A reply deve seguir o tom da mensagem original: cordial, objetiva e curta. "
        "Para alterar ou fora_de_contexto, direcione para o WhatsApp da clínica "
        f"{_CLINIC_WHATSAPP}. "
        "Não invente informações. Não use markdown complexo."
    )

    user_prompt = (
        f"Nome do paciente: {patient_name or 'Paciente'}\n"
        "Mensagem de contexto enviada ao paciente:\n"
        "\"Por favor, responda conforme abaixo: SIM para confirmar presença, "
        "NÃO caso não possa comparecer, REMARCAR para mudar data ou horário.\"\n\n"
        f"Resposta do paciente: {text}\n\n"
        'Formato obrigatório: {"intent":"sim|nao|alterar|fora_de_contexto","reply":"..."}'
    )

    response = await client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=180,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )

    reply = next((block.text for block in response.content if hasattr(block, "text")), "")
    payload = json.loads(reply)
    intent = _normalize_confirmation_intent(payload.get("intent"))
    if intent not in CONFIRMATION_INTENTS:
        raise ValueError(f"Intent inválida retornada pela LLM: {intent}")
    final_reply = (payload.get("reply") or "").strip()
    if not final_reply:
        raise ValueError("Reply vazia retornada pela LLM")
    return {"intent": intent, "reply": final_reply}


async def _update_confirmation(fields: dict[str, Any], confirmation_id: str) -> None:
    db = await get_supabase()
    await db.table("schedule_confirmations").update(fields).eq("id", confirmation_id).execute()


async def _persist_helena_session_id(active: dict[str, Any], message: IncomingMessage) -> str:
    current_session_id = (active.get("helena_session_id") or "").strip()
    incoming_session_id = (message.wts_session_id or "").strip()

    if current_session_id or not incoming_session_id:
        return current_session_id

    try:
        await _update_confirmation({"helena_session_id": incoming_session_id}, active["id"])
        active["helena_session_id"] = incoming_session_id
        logger.info(
            "[CONFIRMATION] helena_session_id persistido | confirmation_id=%s | session_id=%s",
            active["id"],
            incoming_session_id,
        )
        return incoming_session_id
    except Exception as e:
        logger.error(
            "[CONFIRMATION] Erro ao persistir helena_session_id | confirmation_id=%s | session_id=%s | erro=%s",
            active["id"],
            incoming_session_id,
            e,
            exc_info=True,
        )
        return incoming_session_id


async def _complete_helena_confirmation_session(session_id: str | None, appointment_id: str | None) -> None:
    if not session_id:
        logger.warning(
            "[CONFIRMATION] Sessão Helena ausente; conclusão ignorada | appointment_id=%s",
            appointment_id,
        )
        return

    try:
        await complete_session(session_id, reactivate_on_new_message=False, stop_bot_in_execution=True)
    except Exception as e:
        logger.error(
            "[CONFIRMATION] Falha ao concluir sessão Helena | appointment_id=%s | session_id=%s | erro=%s",
            appointment_id,
            session_id,
            e,
            exc_info=True,
        )


async def _find_active_confirmation(message: IncomingMessage) -> dict[str, Any] | None:
    db = await get_supabase()

    for column, value in (("helena_session_id", message.wts_session_id), ("patient_phone", message.patient_phone)):
        if not value:
            continue

        try:
            res = await (
                db.table("schedule_confirmations")
                .select("id, session_id, helena_session_id, patient_phone, patient_name, status, appointment_id")
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
    helena_session_id = await _persist_helena_session_id(active, message)

    try:
        llm_result = await _classify_confirmation_response(message.text, patient_name)
        intent = llm_result["intent"]
        reply = llm_result["reply"]
    except Exception as e:
        logger.warning("Falha ao processar confirmação com LLM, usando fallback: %s", e)
        intent = _normalize_confirmation_intent(_fallback_classify(message.text))
        reply = _fallback_reply(intent, patient_name)

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

    elif intent == "alterar":
        new_status = "sent"

    else:  # fora_de_contexto
        new_status = "sent"  # não finaliza — paciente pode responder SIM/NAO depois

    if new_status != active.get("status"):
        try:
            await _update_confirmation({"status": new_status}, active["id"])
        except Exception as e:
            logger.error("Erro ao atualizar status da confirmação %s: %s", active["id"], e)

    if intent in {"sim", "nao", "alterar"}:
        await _complete_helena_confirmation_session(helena_session_id, appointment_id)

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
        "is_final": intent in {"sim", "nao", "alterar"},
    }


async def handle_confirmation_channel_message(message: IncomingMessage) -> dict[str, Any]:
    """
    Trata mensagens recebidas no canal exclusivo de confirmações.
    Nunca delega para o orquestrador normal.
    """
    result = await handle_confirmation(message)
    if result:
        return result

    return {
        "handled": True,
        "intent": "fora_de_contexto",
        "status": "ignored",
        "reply": _build_out_of_context_reply(message.patient_name),
        "is_final": False,
    }
