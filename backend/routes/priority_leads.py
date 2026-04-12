"""
Endpoints da fila de encaixe prioritário (canetas / endócrino).

Lista, atualiza status e marca como agendado/descartado pela equipe comercial.
"""

import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db.client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_STATUSES = {"aguardando", "em_contato", "agendado", "descartado"}


class UpdatePriorityLead(BaseModel):
    status: Optional[str] = None
    handled_by: Optional[str] = None
    appointment_id: Optional[str] = None
    notes: Optional[str] = None


@router.get("/api/dashboard/priority-leads")
async def list_priority_leads(
    status: Optional[str] = Query(None, description="aguardando|em_contato|agendado|descartado"),
):
    """Lista leads de encaixe prioritário, mais antigos primeiro (FIFO)."""
    try:
        db = await get_supabase()
        query = db.table("priority_leads").select("*")
        if status:
            if status not in VALID_STATUSES:
                raise HTTPException(status_code=400, detail=f"Status inválido. Use: {', '.join(VALID_STATUSES)}")
            query = query.eq("status", status)

        result = await query.order("created_at", desc=False).execute()
        leads = result.data or []

        # Calcula tempo em fila pra cada lead aguardando
        now = datetime.now(timezone.utc)
        for lead in leads:
            try:
                created = datetime.fromisoformat(lead["created_at"].replace("Z", "+00:00"))
                lead["hours_waiting"] = round((now - created).total_seconds() / 3600, 1)
            except Exception:
                lead["hours_waiting"] = None

        # Resumo
        summary = {
            "aguardando": sum(1 for l in leads if l["status"] == "aguardando"),
            "em_contato": sum(1 for l in leads if l["status"] == "em_contato"),
            "agendado":   sum(1 for l in leads if l["status"] == "agendado"),
            "descartado": sum(1 for l in leads if l["status"] == "descartado"),
            "total":      len(leads),
        }

        return {"leads": leads, "summary": summary}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao listar priority leads: %s", e)
        return {"leads": [], "summary": {"aguardando": 0, "em_contato": 0, "agendado": 0, "descartado": 0, "total": 0}}


@router.patch("/api/dashboard/priority-leads/{lead_id}")
async def update_priority_lead(lead_id: str, payload: UpdatePriorityLead):
    """Atualiza status, responsável ou notas de um lead de encaixe."""
    try:
        update: dict = {}

        if payload.status is not None:
            if payload.status not in VALID_STATUSES:
                raise HTTPException(status_code=400, detail=f"Status inválido. Use: {', '.join(VALID_STATUSES)}")
            update["status"] = payload.status
            if payload.status in ("em_contato", "agendado", "descartado"):
                update["handled_at"] = datetime.now(timezone.utc).isoformat()

        if payload.handled_by is not None:
            update["handled_by"] = payload.handled_by
        if payload.appointment_id is not None:
            update["appointment_id"] = payload.appointment_id
        if payload.notes is not None:
            update["notes"] = payload.notes

        if not update:
            raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

        db = await get_supabase()
        result = await db.table("priority_leads").update(update).eq("id", lead_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Lead não encontrado")

        logger.info("[PRIORITY_LEADS] Atualizado | id=%s | update=%s", lead_id, update)
        return {"lead": result.data[0]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao atualizar priority lead %s: %s", lead_id, e)
        raise HTTPException(status_code=500, detail=str(e))
