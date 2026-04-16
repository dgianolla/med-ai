import logging

import httpx

from config import get_settings
from phone_utils import normalize_brazil_phone

logger = logging.getLogger(__name__)


async def trigger_confirmation_chatbot(to_phone: str) -> None:
    """
    Ativa o chatbot da Helena responsável por capturar as respostas no fluxo
    de confirmação.
    """
    settings = get_settings()
    send_url = settings.wts_chatbot_send_url
    chatbot_id = settings.wts_confirmation_chatbot_id
    from_phone = normalize_brazil_phone(settings.wts_confirmation_from_phone)
    normalized_to_phone = normalize_brazil_phone(to_phone)

    if not send_url:
        logger.warning("[HELENA] WTS_CHATBOT_SEND_URL não configurada; pulando trigger")
        return
    if not chatbot_id:
        logger.warning("[HELENA] WTS_CONFIRMATION_CHATBOT_ID não configurado; pulando trigger")
        return
    if not from_phone:
        logger.warning("[HELENA] WTS_CONFIRMATION_FROM_PHONE não configurado; pulando trigger")
        return
    if not normalized_to_phone:
        logger.warning("[HELENA] Telefone de destino ausente/inválido; pulando trigger")
        return

    headers = {
        "accept": "application/json",
        "content-type": "application/*+json",
    }
    if settings.wts_api_key:
        headers["Authorization"] = f"Bearer {settings.wts_api_key}"

    payload = {
        "botKey": chatbot_id,
        "from": from_phone,
        "to": normalized_to_phone,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            send_url,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

    logger.info(
        "[HELENA] Chatbot de confirmação acionado | chatbot_id=%s | from=%s | to=%s",
        chatbot_id,
        from_phone,
        normalized_to_phone,
    )
