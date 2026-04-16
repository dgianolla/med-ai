from datetime import datetime
from db.models import IncomingMessage, MessageType
from phone_utils import normalize_brazil_phone
import logging


logger = logging.getLogger(__name__)


def _normalize_phone(raw: str) -> str:
    """
    Normaliza o telefone do wts.chat para formato limpo.
    Entrada: "+55|11988579353" ou "5511988579353"
    Saída:   "5511988579353"
    """
    return normalize_brazil_phone(raw)


def _detect_type(raw_type: str) -> MessageType:
    """Mapeia tipo do wts.chat para nosso tipo interno."""
    mapping = {
        "TEXT": "text",
        "AUDIO": "audio",
        "IMAGE": "image",
        "VIDEO": "file",   # vídeo tratado como arquivo por enquanto
        "FILE": "file",
        "DOCUMENT": "pdf",
        "PDF": "pdf",
    }
    return mapping.get(raw_type.upper(), "file")


def parse_webhook(body: dict) -> IncomingMessage | None:
    """
    Converte payload do webhook wts.chat em IncomingMessage normalizado.
    Retorna None se a mensagem deve ser ignorada.
    """
    # Formato legado: {"sessionId", "lastMessage", "contact"}
    last_message = body.get("lastMessage", {})
    contact = body.get("contact", {})
    is_legacy_payload = bool(last_message)

    if is_legacy_payload:
        raw_type = last_message.get("type") or "TEXT"
        msg_type = _detect_type(raw_type)
        text = last_message.get("text", "") or ""
        file_url = None

        if msg_type != "text" and not text:
            # Para mídia, o texto será preenchido após transcrição/extração
            # Usamos placeholder por enquanto — o worker vai processar
            file_info = last_message.get("file") or {}
            file_url = file_info.get("url") if isinstance(file_info, dict) else None
            text = f"[{msg_type.upper()}]"

        session_id = body.get("sessionId", "")
        message_id = last_message.get("id", "")
        raw_phone = contact.get("phonenumber", "")
        patient_name = contact.get("name")
        contact_id = str(contact.get("id", ""))
    else:
        # Formato atual observado: {"type":"ReceivedCallback", "phone", "chatLid", "messageId", "text":{"message":"..."}}
        raw_type = "TEXT" if isinstance(body.get("text"), dict) else (body.get("messageType") or "TEXT")
        msg_type = _detect_type(raw_type)

        text_payload = body.get("text")
        if isinstance(text_payload, dict):
            text = text_payload.get("message", "") or ""
        else:
            text = body.get("text", "") or ""

        file_url = None
        session_id = body.get("chatLid") or body.get("sessionId") or ""
        message_id = body.get("messageId", "")
        raw_phone = body.get("phone", "")
        patient_name = body.get("senderName") or body.get("chatName")
        contact_id = body.get("chatLid") or body.get("phone") or ""

    if msg_type == "text" and not text.strip():
        logger.warning(
            "[WEBHOOK_PARSE] Ignorado: texto vazio | sessionId=%s | bodyKeys=%s",
            session_id,
            sorted(body.keys()),
        )
        return None

    if not raw_phone:
        logger.warning(
            "[WEBHOOK_PARSE] Ignorado: telefone ausente | sessionId=%s | contactKeys=%s | bodyKeys=%s",
            session_id,
            sorted(contact.keys()) if isinstance(contact, dict) else [],
            sorted(body.keys()),
        )
        return None

    normalized_phone = _normalize_phone(raw_phone)
    if not normalized_phone:
        logger.warning(
            "[WEBHOOK_PARSE] Ignorado: telefone não normalizado | raw_phone=%s | sessionId=%s",
            raw_phone,
            session_id,
        )
        return None

    logger.info(
        "[WEBHOOK_PARSE] OK | sessionId=%s | phone=%s | type=%s | text=%.80s",
        session_id,
        normalized_phone,
        msg_type,
        text.strip(),
    )

    return IncomingMessage(
        wts_session_id=session_id,
        wts_message_id=message_id,
        patient_phone=normalized_phone,
        patient_name=patient_name,
        wts_contact_id=str(contact_id),
        message_type=msg_type,
        text=text.strip(),
        file_url=file_url,
        received_at=datetime.utcnow(),
    )
