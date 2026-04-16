import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, BackgroundTasks, HTTPException

from db.client import get_supabase
from integrations.scheduling_api import get_agenda
from integrations.whatsapp.wts_client import get_whatsapp_client
from config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()

class TriggerRequest(BaseModel):
    delay_seconds: int = 10
    target_date: Optional[str] = None  # YYYY-MM-DD (defaults to tomorrow)


def _format_appointment_date(date_str: str | None) -> str:
    if not date_str:
        return ""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return date_str


def _format_appointment_time(time_str: str | None) -> str:
    time_str = (time_str or "").strip()
    return time_str[:5] if time_str else ""


def _build_confirmation_message(schedule: dict) -> str:
    patient_name = schedule.get("nome", "Paciente")
    professional_name = ((schedule.get("profissionalSaude") or {}).get("nome") or "seu médico").strip()
    appointment_date = _format_appointment_date(schedule.get("data"))
    appointment_time = _format_appointment_time(schedule.get("horaInicio"))

    return (
        f"Olá, {patient_name}! Tudo bem? 😊\n"
        "Aqui é da Atend Já.\n\n"
        f"Estamos confirmando sua consulta com {professional_name} no dia {appointment_date} às {appointment_time}.\n\n"
        "Por favor, responda conforme abaixo:\n"
        "👉 SIM – para confirmar presença\n"
        "👉 NÃO – caso não possa comparecer\n"
        "👉 REMARCAR – para alterar o horário, fale pelo WhatsApp: (15) 99695-0709\n\n"
        "⚠️ Este canal é exclusivo para confirmação de consultas.\n"
        "❗ Mensagens fora desse escopo não serão respondidas.\n\n"
        "Para dúvidas ou outros assuntos, entre em contato com a clínica pelo nosso canal oficial de atendimento."
    )

async def _dispatch_confirmations(schedules: list, delay_seconds: int):
    """Processa a fila de envios com o atraso configurado."""
    total = len(schedules)
    logger.info("[DISPATCH] Iniciando fila | total=%d | delay=%ds", total, delay_seconds)

    try:
        db = await get_supabase()
        wts_client = get_whatsapp_client()
        channel_id = get_settings().wts_confirmation_channel_id

        if not channel_id:
            logger.error("[DISPATCH] WTS_CONFIRMATION_CHANNEL_ID não configurado — abortando fila")
            return

        sent_count = 0
        skipped_count = 0
        failed_count = 0

        for idx, sched in enumerate(schedules, start=1):
            appointment_id = sched.get("id")
            try:
                phone = (sched.get("telefonePrincipal") or "").strip()
                if not phone:
                    skipped_count += 1
                    logger.info("[DISPATCH] %d/%d pulado (sem telefone) | appointment_id=%s", idx, total, appointment_id)
                    continue

                existing = await db.table("schedule_confirmations").select("id, status").eq("appointment_id", appointment_id).execute()
                if existing.data and existing.data[0]["status"] != "failed":
                    skipped_count += 1
                    logger.info("[DISPATCH] %d/%d pulado (status=%s) | appointment_id=%s", idx, total, existing.data[0]["status"], appointment_id)
                    continue

                if not phone.startswith("55"):
                    phone = "55" + phone

                row = {
                    "session_id": f"conf_{phone}",
                    "patient_name": sched.get("nome", "Paciente"),
                    "patient_phone": phone,
                    "appointment_id": appointment_id,
                    "appointment_date": sched.get("data"),
                    "appointment_time": sched.get("horaInicio"),
                    "professional_name": (sched.get("profissionalSaude") or {}).get("nome", ""),
                    "status": "pending",
                }
                upserted = await db.table("schedule_confirmations").upsert(row, on_conflict="appointment_id").execute()
                conf_id = upserted.data[0]["id"]

                logger.info("[DISPATCH] %d/%d enviando | appointment_id=%s | phone=%s", idx, total, appointment_id, phone)

                try:
                    confirmation_message = _build_confirmation_message(sched)
                    msg_id = await wts_client.send_outbound_text(
                        to_phone=phone,
                        text=confirmation_message,
                        from_channel_id=channel_id,
                    )

                    await db.table("schedule_confirmations").update({
                        "status": "sent",
                        "message_id": msg_id,
                    }).eq("id", conf_id).execute()

                    sent_count += 1
                    logger.info("[DISPATCH] %d/%d enviado | appointment_id=%s | msg_id=%s", idx, total, appointment_id, msg_id)

                except Exception as e:
                    failed_count += 1
                    logger.error("[DISPATCH] %d/%d falha no WTS | appointment_id=%s | erro=%s", idx, total, appointment_id, e, exc_info=True)
                    await db.table("schedule_confirmations").update({"status": "failed"}).eq("id", conf_id).execute()

                await asyncio.sleep(delay_seconds)

            except Exception as e:
                failed_count += 1
                logger.error("[DISPATCH] %d/%d erro no loop | appointment_id=%s | erro=%s", idx, total, appointment_id, e, exc_info=True)

        logger.info(
            "[DISPATCH] Finalizado | total=%d | enviados=%d | pulados=%d | falhas=%d",
            total, sent_count, skipped_count, failed_count,
        )

    except Exception as e:
        logger.error("[DISPATCH] Erro fatal na fila de confirmações: %s", e, exc_info=True)


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
