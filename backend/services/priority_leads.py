"""
Serviço de fila de encaixe prioritário (canetas / endócrino).

Lead de ticket alto que não conseguiu slot na agenda do endocrinologista
nos próximos dias entra nesta fila para a equipe comercial fazer o encaixe
manualmente.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from db.client import get_supabase
from integrations.scheduling_api import get_available_dates

logger = logging.getLogger(__name__)

ENDOCRINO_PROFESSIONAL_ID = 30319
ENDOCRINO_NAME = "Dr. Arthur Wagner"


async def has_endocrino_availability(days_ahead: int = 5) -> bool:
    """
    Verifica se o endocrinologista tem agenda aberta nos próximos N dias.

    Esta é uma checagem grossa: consulta apenas as datas com agenda aberta,
    sem garantir que existem horários livres dentro delas. Suficiente para
    decidir se faz handoff normal pro scheduling ou cai na fila de encaixe.
    """
    today = datetime.now().date()
    target = today + timedelta(days=days_ahead)

    months_to_check: set[tuple[int, int]] = {(today.month, today.year)}
    if target.month != today.month or target.year != today.year:
        months_to_check.add((target.month, target.year))

    all_dates: list[str] = []
    for month, year in months_to_check:
        try:
            dates = await get_available_dates(ENDOCRINO_PROFESSIONAL_ID, month, year)
            all_dates.extend(dates)
        except Exception as e:
            logger.error("Erro ao consultar datas do endócrino %s/%s: %s", month, year, e)
            # Em caso de erro de API, prefira cair na fila de encaixe (lead caro
            # não pode escapar — humano resolve).
            return False

    for d_str in all_dates:
        try:
            d = datetime.strptime(d_str, "%Y-%m-%d").date()
            if today <= d <= target:
                return True
        except ValueError:
            continue

    return False


async def create_priority_lead(
    *,
    patient_id: Optional[str],
    session_id: Optional[str],
    patient_name: Optional[str],
    patient_phone: str,
    caneta_preferida: Optional[str] = None,
    periodo_preferido: Optional[str] = None,
    notes: Optional[str] = None,
) -> Optional[dict]:
    """Insere um lead na fila de encaixe prioritário."""
    try:
        db = await get_supabase()
        result = await db.table("priority_leads").insert({
            "patient_id": patient_id,
            "session_id": session_id,
            "patient_name": patient_name,
            "patient_phone": patient_phone,
            "interest": "canetas",
            "caneta_preferida": caneta_preferida,
            "periodo_preferido": periodo_preferido,
            "professional_id": ENDOCRINO_PROFESSIONAL_ID,
            "professional_name": ENDOCRINO_NAME,
            "notes": notes,
            "status": "aguardando",
        }).execute()
        row = result.data[0] if result.data else None
        logger.info(
            "✅ PRIORITY LEAD criado | phone=%s | caneta=%s | id=%s",
            patient_phone, caneta_preferida, row.get("id") if row else None,
        )
        return row
    except Exception as e:
        logger.error("Erro ao criar priority lead: %s", e)
        return None
