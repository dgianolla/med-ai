import logging

import httpx

from config import get_settings

logger = logging.getLogger(__name__)


async def trigger_confirmation_chatbot() -> None:
    """
    Ativa o chatbot da Helena responsável por capturar as respostas no fluxo
    de confirmação.
    """
    settings = get_settings()
    send_url = settings.wts_chatbot_send_url
    chatbot_id = settings.wts_confirmation_chatbot_id

    if not send_url:
        logger.warning("[HELENA] WTS_CHATBOT_SEND_URL não configurada; pulando trigger")
        return
    if not chatbot_id:
        logger.warning("[HELENA] WTS_CONFIRMATION_CHATBOT_ID não configurado; pulando trigger")
        return

    headers = {
        "accept": "application/json",
        "content-type": "application/*+json",
    }
    if settings.wts_api_key:
        headers["Authorization"] = f"Bearer {settings.wts_api_key}"

    payload = {"id": chatbot_id}

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            send_url,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

    logger.info("[HELENA] Chatbot de confirmação acionado | chatbot_id=%s", chatbot_id)
