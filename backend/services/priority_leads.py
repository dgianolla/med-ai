"""
Serviço de fila de atenção comercial prioritária.

Reúne dois cenários:
1. Leads de alto ticket sem vaga próxima (ex: canetas / endocrino)
2. Pacientes já agendados que merecem destaque operacional no frontend

Os cards são consumidos pelo painel para contato humano e eventual avaliação
de encaixe/remanejamento, sem alterar o fluxo padrão de agendamento.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from anthropic import AsyncAnthropic

from config import get_settings
from db.client import get_supabase
from integrations.scheduling_api import get_available_dates

logger = logging.getLogger(__name__)

ENDOCRINO_PROFESSIONAL_ID = 30319
ENDOCRINO_NAME = "Dr. Arthur Wagner"
OPEN_STATUSES = {"aguardando", "em_contato"}


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


def _classify_priority(
    *,
    source_agent: Optional[str],
    interest: Optional[str],
    convenio: Optional[str],
    campaign_name: Optional[str],
) -> tuple[str, int, str]:
    source = (source_agent or "").lower()
    convenio_norm = (convenio or "").lower()
    interest_norm = (interest or "").lower()

    if source == "weight_loss" or interest_norm == "canetas":
        return (
            "high_ticket",
            100,
            "Avaliar encaixe prioritario e contato comercial rapido.",
        )

    if source == "campaign" or campaign_name:
        return (
            "campaign_hot_lead",
            80,
            "Avaliar prioridade comercial e possivel antecipacao de agenda.",
        )

    if convenio_norm in {"", "particular"}:
        return (
            "private_patient",
            60,
            "Paciente particular. Avaliar oportunidade de antecipacao ou remanejamento.",
        )

    return (
        "operational_attention",
        40,
        "Monitorar lead e avaliar prioridade comercial conforme contexto.",
    )


def _conversation_excerpt(conversation_history: list[dict], max_messages: int = 6) -> str:
    excerpt: list[str] = []
    for msg in conversation_history[-max_messages:]:
        role = "Paciente" if msg.get("role") == "user" else "LIA"
        content = (msg.get("content") or "").strip()
        if content:
            excerpt.append(f"{role}: {content[:240]}")
    return "\n".join(excerpt)


def _fallback_summary(
    *,
    patient_name: Optional[str],
    specialty: Optional[str],
    priority_type: str,
    action_label: str,
    campaign_name: Optional[str],
) -> str:
    patient_label = patient_name or "Paciente"
    if priority_type == "high_ticket":
        return (
            f"{patient_label} e um lead de alto ticket"
            f"{f' em {specialty}' if specialty else ''}. {action_label}"
        )
    if priority_type == "campaign_hot_lead":
        campaign_piece = f" da campanha {campaign_name}" if campaign_name else ""
        return f"{patient_label} veio{campaign_piece} e merece atencao comercial. {action_label}"
    if priority_type == "private_patient":
        return f"{patient_label} e paciente particular{f' de {specialty}' if specialty else ''}. {action_label}"
    return f"{patient_label} precisa de acompanhamento operacional. {action_label}"


async def _generate_priority_summary(
    *,
    patient_name: Optional[str],
    specialty: Optional[str],
    source_agent: Optional[str],
    convenio: Optional[str],
    interest: Optional[str],
    campaign_name: Optional[str],
    priority_type: str,
    action_label: str,
    notes: Optional[str],
    conversation_history: Optional[list[dict]],
) -> str:
    fallback = _fallback_summary(
        patient_name=patient_name,
        specialty=specialty,
        priority_type=priority_type,
        action_label=action_label,
        campaign_name=campaign_name,
    )

    try:
        settings = get_settings()
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        prompt = (
            "Gere um resumo operacional curto para um card interno de clinica.\n"
            "Regras:\n"
            "- resposta em portugues\n"
            "- no maximo 2 frases\n"
            "- tom objetivo, sem floreio\n"
            "- deixar claro por que o card merece atencao\n"
            "- incluir sugestao de acao humana quando fizer sentido\n"
            "- nao inventar fatos ausentes\n\n"
            f"Paciente: {patient_name or 'Nao informado'}\n"
            f"Especialidade: {specialty or 'Nao informada'}\n"
            f"Origem: {source_agent or 'Nao informada'}\n"
            f"Convenio: {convenio or 'Nao informado'}\n"
            f"Interesse: {interest or 'Nao informado'}\n"
            f"Campanha: {campaign_name or 'Nao se aplica'}\n"
            f"Tipo de prioridade: {priority_type}\n"
            f"Acao sugerida: {action_label}\n"
            f"Observacoes: {notes or 'Nenhuma'}\n"
            "Historico recente:\n"
            f"{_conversation_excerpt(conversation_history or []) or 'Sem historico relevante'}\n"
        )

        response = await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=140,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        summary = next((b.text for b in response.content if hasattr(b, "text")), None)
        summary = (summary or "").strip()
        return summary or fallback
    except Exception as e:
        logger.warning("Resumo LLM de priority lead falhou; usando fallback | error=%s", e)
        return fallback


async def create_priority_lead(
    *,
    patient_id: Optional[str],
    session_id: Optional[str],
    patient_name: Optional[str],
    patient_phone: str,
    interest: Optional[str] = None,
    convenio: Optional[str] = None,
    specialty: Optional[str] = None,
    source_agent: Optional[str] = None,
    campaign_name: Optional[str] = None,
    caneta_preferida: Optional[str] = None,
    periodo_preferido: Optional[str] = None,
    professional_id: Optional[int] = None,
    professional_name: Optional[str] = None,
    notes: Optional[str] = None,
    action_label: Optional[str] = None,
    summary: Optional[str] = None,
    priority_type: Optional[str] = None,
    priority_score: Optional[int] = None,
    appointment_id: Optional[str] = None,
    conversation_history: Optional[list[dict]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[dict]:
    """Cria ou atualiza um card de atencao comercial prioritario."""
    try:
        db = await get_supabase()

        resolved_type, resolved_score, default_action = _classify_priority(
            source_agent=source_agent,
            interest=interest,
            convenio=convenio,
            campaign_name=campaign_name,
        )
        priority_type = priority_type or resolved_type
        priority_score = priority_score if priority_score is not None else resolved_score
        action_label = action_label or default_action

        summary = summary or await _generate_priority_summary(
            patient_name=patient_name,
            specialty=specialty,
            source_agent=source_agent,
            convenio=convenio,
            interest=interest,
            campaign_name=campaign_name,
            priority_type=priority_type,
            action_label=action_label,
            notes=notes,
            conversation_history=conversation_history,
        )

        existing_rows: list[dict] = []
        if session_id:
            result = await db.table("priority_leads").select("*").eq("session_id", session_id).execute()
            existing_rows = result.data or []
        elif patient_phone:
            result = await db.table("priority_leads").select("*").eq("patient_phone", patient_phone).execute()
            existing_rows = result.data or []

        open_existing = next(
            (row for row in existing_rows if row.get("status") in OPEN_STATUSES),
            None,
        )

        payload = {
            "patient_id": patient_id,
            "session_id": session_id,
            "patient_name": patient_name,
            "patient_phone": patient_phone,
            "interest": interest or "consulta",
            "convenio": convenio,
            "specialty": specialty,
            "source_agent": source_agent,
            "campaign_name": campaign_name,
            "caneta_preferida": caneta_preferida,
            "periodo_preferido": periodo_preferido,
            "professional_id": professional_id,
            "professional_name": professional_name,
            "notes": notes,
            "summary": summary,
            "action_label": action_label,
            "priority_type": priority_type,
            "priority_score": priority_score,
            "status": open_existing.get("status") if open_existing else "aguardando",
            "appointment_id": appointment_id,
            "metadata": metadata,
        }

        if open_existing:
            result = await db.table("priority_leads").update(payload).eq("id", open_existing["id"]).execute()
            row = result.data[0] if result.data else open_existing
            logger.info(
                "♻️ PRIORITY LEAD atualizado | id=%s | phone=%s | type=%s | source=%s",
                open_existing["id"], patient_phone, priority_type, source_agent,
            )
            return row

        result = await db.table("priority_leads").insert(payload).execute()
        row = result.data[0] if result.data else None
        logger.info(
            "✅ PRIORITY LEAD criado | phone=%s | type=%s | source=%s | id=%s",
            patient_phone, priority_type, source_agent, row.get("id") if row else None,
        )
        return row
    except Exception as e:
        logger.error("Erro ao criar priority lead: %s", e)
        return None
