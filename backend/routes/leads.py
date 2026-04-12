from fastapi import APIRouter, Query
from db.client import get_supabase
import logging
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()

SPECIALTIES = [
    "clinica_geral",
    "cardiologia",
    "psiquiatria",
    "endocrinologia",
    "ginecologia",
    "dermatologia",
    "otorrinolaringologia",
]


def _extract_specialty(session_row: dict) -> Optional[str]:
    """Extract specialty from session handoff_payload or patient_metadata."""
    if not session_row:
        return None
    handoff = session_row.get("handoff_payload") or {}
    metadata = session_row.get("patient_metadata") or {}
    return (
        handoff.get("specialty_needed")
        or metadata.get("specialty")
        or None
    )


@router.get("/api/dashboard/leads")
async def get_leads(
    status: Optional[str] = Query(None, description="qualified|disqualified"),
    specialty: Optional[str] = Query(None, description="Filter by specialty key"),
    date_from: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
):
    """
    Retorna leads qualificados e desqualificados.

    Qualificados: schedule_confirmations com status='confirmed'
    Desqualificados: sessions completed que passaram por cancellation ou tem confirmations com status='canceled'
    """
    try:
        db = await get_supabase()
        leads = []

        # ── Qualified leads: confirmed appointments ──
        query = db.table("schedule_confirmations").select(
            "id, session_id, patient_name, patient_phone, "
            "appointment_id, appointment_date, appointment_time, "
            "professional_name, status, created_at"
        ).eq("status", "confirmed")

        if date_from:
            query = query.gte("appointment_date", date_from)
        if date_to:
            query = query.lte("appointment_date", date_to)

        result = await query.order("created_at", desc=True).execute()

        for conf in result.data or []:
            # Busca sessão associada para extrair specialty do handoff
            session_data = None
            if conf.get("session_id"):
                sess_res = await (
                    db.table("sessions")
                    .select("handoff_payload, patient_metadata")
                    .eq("id", conf["session_id"])
                    .limit(1)
                    .execute()
                )
                if sess_res.data:
                    session_data = sess_res.data[0]

            specialty = _extract_specialty(session_data)

            leads.append({
                "patient_name": conf.get("patient_name", ""),
                "patient_phone": conf.get("patient_phone", ""),
                "specialty": specialty,
                "status": "qualified",
                "disqualification_reason": None,
                "scheduled_date": conf.get("appointment_date"),
                "scheduled_time": conf.get("appointment_time"),
                "professional_name": conf.get("professional_name", ""),
                "appointment_id": conf.get("appointment_id"),
                "created_at": conf.get("created_at", ""),
                "session_id": conf.get("session_id", ""),
            })

        # ── Disqualified leads: canceled confirmations ──
        cancel_query = db.table("schedule_confirmations").select(
            "id, session_id, patient_name, patient_phone, "
            "appointment_id, appointment_date, appointment_time, "
            "professional_name, status, created_at"
        ).eq("status", "canceled")

        if date_from:
            cancel_query = cancel_query.gte("appointment_date", date_from)
        if date_to:
            cancel_query = cancel_query.lte("appointment_date", date_to)

        cancel_result = await cancel_query.order("created_at", desc=True).execute()

        # Track seen phone+appointment combos to avoid duplicates
        seen_disqualified = set()

        for conf in cancel_result.data or []:
            key = f"{conf.get('patient_phone')}_{conf.get('appointment_id')}"
            if key in seen_disqualified:
                continue
            seen_disqualified.add(key)

            session_data = None
            if conf.get("session_id"):
                sess_res = await (
                    db.table("sessions")
                    .select("handoff_payload, patient_metadata")
                    .eq("id", conf["session_id"])
                    .limit(1)
                    .execute()
                )
                if sess_res.data:
                    session_data = sess_res.data[0]

            specialty = _extract_specialty(session_data)

            leads.append({
                "patient_name": conf.get("patient_name", ""),
                "patient_phone": conf.get("patient_phone", ""),
                "specialty": specialty,
                "status": "disqualified",
                "disqualification_reason": "cancelled",
                "scheduled_date": conf.get("appointment_date"),
                "scheduled_time": conf.get("appointment_time"),
                "professional_name": conf.get("professional_name", ""),
                "appointment_id": conf.get("appointment_id"),
                "created_at": conf.get("created_at", ""),
                "session_id": conf.get("session_id", ""),
            })

        # ── Filter by status if provided ──
        if status == "qualified":
            leads = [l for l in leads if l["status"] == "qualified"]
        elif status == "disqualified":
            leads = [l for l in leads if l["status"] == "disqualified"]

        # ── Filter by specialty if provided ──
        if specialty and specialty in SPECIALTIES:
            leads = [l for l in leads if l.get("specialty") == specialty]

        # ── Build summary ──
        qualified_count = sum(1 for l in leads if l["status"] == "qualified")
        disqualified_count = sum(1 for l in leads if l["status"] == "disqualified")

        by_specialty: dict = {}
        # Include all leads (not just filtered) for accurate summary
        all_leads = leads  # if filtered, this is already filtered; that's fine for UI
        for l in all_leads:
            spec = l.get("specialty") or "sem_especialidade"
            if spec not in by_specialty:
                by_specialty[spec] = {"qualified": 0, "disqualified": 0}
            if l["status"] == "qualified":
                by_specialty[spec]["qualified"] += 1
            else:
                by_specialty[spec]["disqualified"] += 1

        return {
            "leads": leads,
            "summary": {
                "qualified": qualified_count,
                "disqualified": disqualified_count,
                "by_specialty": by_specialty,
            },
        }

    except Exception as e:
        logger.error("Erro ao buscar leads: %s", e)
        return {"leads": [], "summary": {"qualified": 0, "disqualified": 0, "by_specialty": {}}}
