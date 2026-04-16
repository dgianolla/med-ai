from datetime import datetime
from db.models import IncomingMessage, MessageType
from phone_utils import normalize_brazil_phone


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
    last_message = body.get("lastMessage", {})
    contact = body.get("contact", {})

    # Ignorar se não há mensagem
    if not last_message:
        return None

    raw_type = last_message.get("type") or "TEXT"
    msg_type = _detect_type(raw_type)

    # Ignorar texto vazio
    text = last_message.get("text", "") or ""
    file_url = None

    if msg_type != "text" and not text:
        # Para mídia, o texto será preenchido após transcrição/extração
        # Usamos placeholder por enquanto — o worker vai processar
        file_info = last_message.get("file") or {}
        file_url = file_info.get("url") if isinstance(file_info, dict) else None
        text = f"[{msg_type.upper()}]"  # placeholder até processar

    if msg_type == "text" and not text.strip():
        return None

    raw_phone = contact.get("phonenumber", "")
    if not raw_phone:
        return None

    return IncomingMessage(
        wts_session_id=body.get("sessionId", ""),
        wts_message_id=last_message.get("id", ""),
        patient_phone=_normalize_phone(raw_phone),
        patient_name=contact.get("name"),
        wts_contact_id=str(contact.get("id", "")),
        message_type=msg_type,
        text=text.strip(),
        file_url=file_url,
        received_at=datetime.utcnow(),
    )
