import logging

import httpx

from config import get_settings
from phone_utils import normalize_brazil_phone

logger = logging.getLogger(__name__)


def _helena_headers() -> dict[str, str]:
    settings = get_settings()
    headers = {
        "accept": "application/json",
        "content-type": "application/*+json",
    }
    if settings.wts_api_key:
        headers["Authorization"] = f"Bearer {settings.wts_api_key}"
    return headers


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

    payload = {
        "botKey": chatbot_id,
        "from": from_phone,
        "to": normalized_to_phone,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            send_url,
            headers=_helena_headers(),
            json=payload,
        )
        response.raise_for_status()

    logger.info(
        "[HELENA] Chatbot de confirmação acionado | chatbot_id=%s | from=%s | to=%s",
        chatbot_id,
        from_phone,
        normalized_to_phone,
    )


async def complete_session(
    session_id: str,
    *,
    reactivate_on_new_message: bool = False,
    stop_bot_in_execution: bool = True,
) -> dict:
    """Conclui uma sessão da Helena e interrompe o chatbot atual."""
    settings = get_settings()
    session_id = (session_id or "").strip()
    if not session_id:
        raise ValueError("session_id é obrigatório para concluir a sessão Helena")

    payload = {
        "reactivateOnNewMessage": reactivate_on_new_message,
        "stopBotInExecution": stop_bot_in_execution,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.put(
            f"{settings.helena_api_base_url}/chat/v1/session/{session_id}/complete",
            headers=_helena_headers(),
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    logger.info(
        "[HELENA] Sessão concluída | session_id=%s | stop_bot_in_execution=%s | reactivate_on_new_message=%s",
        session_id,
        stop_bot_in_execution,
        reactivate_on_new_message,
    )
    return data
