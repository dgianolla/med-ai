import logging
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from integrations.whatsapp import parse_webhook

logger = logging.getLogger(__name__)
router = APIRouter()


async def _process_message(body: dict):
    """Processa mensagem em background após resposta 200 ao wts.chat."""
    from agents.confirmation_agent import handle_confirmation
    from integrations.whatsapp import parse_webhook
    from integrations.whatsapp import get_whatsapp_client
    from orchestrator.orchestrator import dispatch

    logger.info(
        "[WEBHOOK] Background start | sessionId=%s | keys=%s",
        body.get("sessionId", ""),
        sorted(body.keys()),
    )

    incoming = parse_webhook(body)
    if not incoming:
        logger.warning(
            "[WEBHOOK] Payload ignorado pelo parser | sessionId=%s | keys=%s",
            body.get("sessionId", ""),
            sorted(body.keys()),
        )
        return

    logger.info(
        "Mensagem recebida | phone=%s | type=%s | session=%s | text=%.80s",
        incoming.patient_phone,
        incoming.message_type,
        incoming.wts_session_id,
        incoming.text,
    )

    try:
        confirmation_result = await handle_confirmation(incoming)
    except Exception as e:
        logger.error("Erro no agente de confirmação; seguindo para orquestração normal: %s", e, exc_info=True)
        confirmation_result = None

    if confirmation_result:
        logger.info(
            "Mensagem tratada pelo agente de confirmação | phone=%s | intent=%s | status=%s",
            incoming.patient_phone,
            confirmation_result["intent"],
            confirmation_result["status"],
        )
        try:
            whatsapp = get_whatsapp_client()
            await whatsapp.send_text(
                session_id=incoming.wts_session_id,
                text=confirmation_result["reply"],
                ref_id=incoming.wts_message_id,
            )
        except Exception as e:
            logger.error("Erro ao enviar resposta de confirmação via wts.chat: %s", e)
        return

    await dispatch(incoming)


@router.post("/webhook/message")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint chamado pelo wts.chat a cada mensagem recebida.
    Responde 200 imediatamente e processa em background.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload inválido")

    logger.info(
        "[WEBHOOK] Request recebida | sessionId=%s | keys=%s",
        body.get("sessionId", ""),
        sorted(body.keys()) if isinstance(body, dict) else [],
    )

    # Responde 200 imediatamente para o wts.chat não retentar
    background_tasks.add_task(_process_message, body)
    return {"status": "received"}


@router.get("/health")
async def health():
    return {"status": "ok"}
