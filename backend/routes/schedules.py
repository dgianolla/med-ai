import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, BackgroundTasks, HTTPException

from db.client import get_supabase
from integrations.scheduling_api import get_agenda
from integrations.whatsapp.wts_client import get_confirmation_whatsapp_client

logger = logging.getLogger(__name__)
router = APIRouter()

class TriggerRequest(BaseModel):
    delay_seconds: int = 10
    target_date: Optional[str] = None  # YYYY-MM-DD (defaults to tomorrow)


def _format_confirmation_datetime(date_str: str | None, time_str: str | None) -> str:
    if not date_str and not time_str:
        return "no horario agendado"

    formatted_date = date_str or ""
    try:
        if date_str:
            formatted_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        formatted_date = date_str or ""

    formatted_time = (time_str or "").strip()
    if formatted_time:
        formatted_time = formatted_time[:5]

    if formatted_date and formatted_time:
        return f"no dia {formatted_date} as {formatted_time}"
    if formatted_date:
        return f"no dia {formatted_date}"
    return f"as {formatted_time}"


def _build_confirmation_message(schedule: dict) -> str:
    patient_name = schedule.get("nome", "Paciente")
    professional_name = (schedule.get("profissionalSaude") or {}).get("nome", "seu profissional")
    appointment_when = _format_confirmation_datetime(
        schedule.get("data"),
        schedule.get("horaInicio"),
    )

    return (
        f"Olá, {patient_name}! Aqui é da Atend Já.\n\n"
        f"Estamos confirmando sua consulta com {professional_name} {appointment_when}.\n\n"
        "Se estiver tudo certo, responda SIM.\n"
        "Se não puder comparecer, responda NÃO.\n"
        "Se precisar de outro horário, responda REMARCAR.\n\n"
        "Este canal é exclusivo para confirmação de consultas.\n"
        "Para dúvidas ou outros assuntos, fale com a clínica pelo canal oficial de atendimento."
    )

async def _dispatch_confirmations(schedules: list, delay_seconds: int):
    """Processa a fila de envios com o atraso configurado."""
    db = await get_supabase()
    wts_client = get_confirmation_whatsapp_client()
    
    for sched in schedules:
        try:
            # Pula se o telefone for vazio
            phone = sched.get("telefonePrincipal", "").strip()
            if not phone:
                continue
                
            # Verifica se já existe para não enviar duplicado
            existing = await db.table("schedule_confirmations").select("id, status").eq("appointment_id", sched["id"]).execute()
            if existing.data and existing.data[0]["status"] != "failed":
                continue # Já foi enviado ou está na fila
                
            # Formata numero
            if not phone.startswith("55"):
                phone = "55" + phone
                
            # Cria sessão no WTS (usando o endpoint corenato ou assumindo que o template_id resolve o start)
            # O start session geralmente precisa do telefone
            # Como send_template no WTS precisa do session_id, se a sessao nao existe, ela deveria ser criada, ou podemos usar o numero.
            # No wts.chat, para templates usa-se o envio para o número
            session_id = f"conf_{phone}" # Mock: a integracao WTS precisaria criar sessao ativa. 
            
            # Adiciona ao DB como pending
            data_insert = {
                "session_id": session_id,
                "patient_name": sched.get("nome", "Paciente"),
                "patient_phone": phone,
                "appointment_id": sched.get("id"),
                "appointment_date": sched.get("data"),
                "appointment_time": sched.get("horaInicio"),
                "professional_name": sched.get("profissionalSaude", {}).get("nome", ""),
                "status": "pending"
            }
            res = await db.table("schedule_confirmations").insert(data_insert).execute()
            conf_id = res.data[0]["id"]
            
            try:
                confirmation_message = _build_confirmation_message(sched)
                msg_id = await wts_client.send_text(
                    session_id=phone, # Usando o telefone como referencia inicial
                    text=confirmation_message,
                )
                
                # Update success
                await db.table("schedule_confirmations").update({
                    "status": "sent",
                    "message_id": msg_id,
                    "session_id": phone # atualiza a sessao correta
                }).eq("id", conf_id).execute()
                
            except Exception as e:
                logger.error(f"Erro ao disparar WTS: {e}")
                await db.table("schedule_confirmations").update({"status": "failed"}).eq("id", conf_id).execute()
            
            # Espera o delay configurado
            await asyncio.sleep(delay_seconds)
            
        except Exception as e:
            logger.error(f"Erro no dispatch loop para agenda {sched.get('id')}: {e}")


@router.post("/api/schedules/trigger-confirmations")
async def trigger_confirmations(req: TriggerRequest, background_tasks: BackgroundTasks):
    """Busca as agendas e dispara a fila de envio."""
    try:
        target = req.target_date
        if not target:
            # Amanhã
            target = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            
        schedules = await get_agenda(target, target)
        
        # Inicia background task
        background_tasks.add_task(_dispatch_confirmations, schedules, req.delay_seconds)
        
        return {"status": "started", "target_date": target, "total_schedules_found": len(schedules)}
        
    except Exception as e:
        logger.error(f"Erro ao iniciar trigger de confirmacao: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao agendar")


@router.get("/api/schedules/confirmations")
async def get_confirmations(date: str):
    """Retorna o status dos envios para acompanhamento no painel."""
    try:
        db = await get_supabase()
        res = await db.table("schedule_confirmations").select("*").eq("appointment_date", date).order("created_at", desc=True).execute()
        return {"confirmations": res.data or []}
    except Exception as e:
        logger.error(f"Erro ao listar confirmacoes: {e}")
        return {"confirmations": []}


@router.get("/api/schedules/preview")
async def preview_schedules(date: str):
    """Retorna todos os agendamentos da API mesclados com o status no Supabase."""
    try:
        logger.info("[PREVIEW] Buscando agenda para date=%s", date)

        # Busca da API AppHealth
        schedules = await get_agenda(date, date)
        logger.info("[PREVIEW] AppHealth retornou %d agendamentos", len(schedules))

        # Debug: log da estrutura do primeiro agendamento (se existir)
        if schedules:
            logger.info("[PREVIEW] Exemplo de agendamento: %s", str(schedules[0])[:500])
        else:
            logger.warning("[PREVIEW] Nenhum agendamento retornado pela AppHealth para %s", date)

        status_map = {}
        try:
            # Falhas no Supabase nao devem derrubar o preview da agenda.
            db = await get_supabase()
            db_res = await db.table("schedule_confirmations").select("appointment_id, status").eq("appointment_date", date).execute()
            status_map = {item["appointment_id"]: item["status"] for item in (db_res.data or [])}
            logger.info("[PREVIEW] Supabase retornou %d status existentes", len(status_map))
        except Exception as e:
            logger.warning("[PREVIEW] Erro ao buscar status no BD (seguindo sem status): %s", e)

        preview = []
        skipped_no_phone = 0
        for sched in schedules:
            app_id = sched.get("id")
            phone = sched.get("telefonePrincipal", "")
            if not phone:
                skipped_no_phone += 1
                continue # Pula se nao tiver telefone

            preview.append({
                "appointment_id": app_id,
                "patient_name": sched.get("nome", "Paciente"),
                "patient_phone": phone,
                "appointment_time": sched.get("horaInicio"),
                "professional_name": (sched.get("profissionalSaude") or {}).get("nome", ""),
                "status": status_map.get(app_id, "not_started") # not_started significa que nao ta na fila ainda
            })

        preview.sort(key=lambda x: x.get("appointment_time", ""))

        logger.info(
            "[PREVIEW] Resultado: %d agendamentos com telefone, %d pulados sem telefone",
            len(preview), skipped_no_phone,
        )

        return {"schedules": preview}
    except Exception as e:
        logger.error(f"[PREVIEW] Erro ao carregar preview da agenda: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao carregar preview da agenda: {str(e)}")
