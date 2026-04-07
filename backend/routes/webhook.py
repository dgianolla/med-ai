import logging
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from integrations.whatsapp import parse_webhook

logger = logging.getLogger(__name__)
router = APIRouter()


async def _process_message(body: dict):
    """Processa mensagem em background após resposta 200 ao wts.chat."""
    from integrations.whatsapp import parse_webhook
    from orchestrator.orchestrator import dispatch

    incoming = parse_webhook(body)
    if not incoming:
        return

    logger.info(
        "Mensagem recebida | phone=%s | type=%s | session=%s | text=%.80s",
        incoming.patient_phone,
        incoming.message_type,
        incoming.wts_session_id,
        incoming.text,
    )

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

    # Responde 200 imediatamente para o wts.chat não retentar
    background_tasks.add_task(_process_message, body)
    return {"status": "received"}


@router.get("/health")
async def health():
    return {"status": "ok"}
