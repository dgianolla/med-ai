import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from integrations.whatsapp import parse_webhook

logger = logging.getLogger(__name__)
router = APIRouter()


async def _process_confirmation_message(body: dict):
    """Processa mensagem do canal exclusivo de confirmações."""
    from agents.confirmation_agent import handle_confirmation_channel_message
    from integrations.whatsapp import get_whatsapp_client

    logger.info(
        "[CONFIRMATION_WEBHOOK] Background start | sessionId=%s | keys=%s",
        body.get("sessionId", body.get("chatLid", "")),
        sorted(body.keys()),
    )

    incoming = parse_webhook(body)
    if not incoming:
        logger.warning(
            "[CONFIRMATION_WEBHOOK] Payload ignorado pelo parser | sessionId=%s | keys=%s",
            body.get("sessionId", body.get("chatLid", "")),
            sorted(body.keys()),
        )
        return

    logger.info(
        "[CONFIRMATION_WEBHOOK] Mensagem recebida | phone=%s | type=%s | session=%s | text=%.80s",
        incoming.patient_phone,
        incoming.message_type,
        incoming.wts_session_id,
        incoming.text,
    )

    try:
        result = await handle_confirmation_channel_message(incoming)
        logger.info(
            "[CONFIRMATION_WEBHOOK] Mensagem tratada | phone=%s | intent=%s | status=%s",
            incoming.patient_phone,
            result["intent"],
            result["status"],
        )

        whatsapp = get_whatsapp_client()
        await whatsapp.send_text(
            session_id=incoming.wts_session_id,
            text=result["reply"],
            ref_id=incoming.wts_message_id,
        )
    except Exception as e:
        logger.error(
            "[CONFIRMATION_WEBHOOK] Erro ao processar mensagem de confirmação: %s",
            e,
            exc_info=True,
        )


@router.post("/webhook/confirmations")
async def receive_confirmation_message(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint exclusivo para mensagens do canal de confirmações.
    Responde 200 imediatamente e processa em background.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload inválido")

    logger.info(
        "[CONFIRMATION_WEBHOOK] Request recebida | sessionId=%s | keys=%s",
        body.get("sessionId", body.get("chatLid", "")),
        sorted(body.keys()) if isinstance(body, dict) else [],
    )

    background_tasks.add_task(_process_confirmation_message, body)
    return {"status": "received"}
