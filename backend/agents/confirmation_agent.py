import logging
import re
from typing import Dict, Any
from integrations.whatsapp import incoming_message
from config import get_settings

logger = logging.getLogger(__name__)

async def handle_confirmation(message: incoming_message.IncomingMessage) -> Dict[str, Any]:
    """
    Agente especialista em confirmação de consultas.
    Neste projeto, não usamos Anthropic para este agente; ele segue um fluxo determinístico
    ou regras simples baseadas em regex, já que esperamos respostas como "Sim", "Confirmo", "Não", "Cancelar".
    """
    text = (message.text or "").lower().strip()
    
    # Detecção simples de intenção
    is_confirm = bool(re.search(r'\b(sim|confirmo|confirmar|confirmado|ok|certeza)\b', text))
    is_cancel = bool(re.search(r'\b(n[ãa]o|cancelar|cancela|desmarcar|remarcar)\b', text))
    
    if is_confirm:
        reply = "Excelente! Sua consulta está confirmada. Nos vemos lá!"
        status = "confirmed"
    elif is_cancel:
        reply = "Tudo bem, sua consulta foi cancelada/desmarcada. Se desejar remarcar, entre em contato com nossa central."
        status = "canceled"
    else:
        reply = "Por favor, responda apenas com 'Sim' para confirmar sua consulta ou 'Não' para cancelar."
        status = "pending"

    # Atualiza o status no Supabase
    from db.client import get_supabase
    db = await get_supabase()

    try:
        # Busca a confirmação ativa por session_id
        session_id = message.wts_session_id
        schedule_res = await db.table("schedule_confirmations").select("id").eq("session_id", session_id).order("created_at", desc=True).limit(1).execute()

        if schedule_res.data and status in ["confirmed", "canceled"]:
            conf_id = schedule_res.data[0]["id"]
            await db.table("schedule_confirmations").update({"status": status}).eq("id", conf_id).execute()
    except Exception as e:
        logger.error(f"Erro ao atualizar status da confirmação para {session_id}: {e}")

    # Retorna o texto para ser enviado de volta ao paciente
    return {
        "text": reply,
        "is_final": status in ["confirmed", "canceled"],
        "new_agent": None
    }
