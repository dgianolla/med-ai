from fastapi import APIRouter
from db.client import get_supabase
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/dashboard/sessions")
async def get_sessions():
    """
    Retorna sessões ativas para o painel CRM.
    Usa a view active_sessions_view do Supabase.
    """
    try:
        db = await get_supabase()
        result = await (
            db.table("active_sessions_view")
            .select("*")
            .order("last_activity_at", desc=True)
            .execute()
        )
        return {"sessions": result.data or []}
    except Exception as e:
        logger.error("Erro ao buscar sessões: %s", e)
        return {"sessions": []}


@router.get("/api/dashboard/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """Retorna histórico de mensagens de uma sessão."""
    try:
        db = await get_supabase()
        result = await (
            db.table("messages")
            .select("role, content, agent_id, message_type, created_at")
            .eq("session_id", session_id)
            .order("created_at")
            .execute()
        )
        return {"messages": result.data or []}
    except Exception as e:
        logger.error("Erro ao buscar mensagens: %s", e)
        return {"messages": []}
