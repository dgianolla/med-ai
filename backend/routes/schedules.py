import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from config import get_settings
from db.client import get_supabase
from integrations.helena_client import send_confirmation_template_batch
from integrations.scheduling_api import get_agenda
from phone_utils import normalize_brazil_phone
from time_utils import clinic_now

logger = logging.getLogger(__name__)
router = APIRouter()


class TriggerRequest(BaseModel):
    delay_seconds: int = 300
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


def _chunk_list(items: list, size: int) -> list[list]:
    return [items[idx:idx + size] for idx in range(0, len(items), size)]


def _build_template_parameters(schedule: dict) -> dict[str, str]:
    return {
        "MEDICO": ((schedule.get("profissionalSaude") or {}).get("nome") or "seu médico").strip(),
        "DATA": _format_appointment_date(schedule.get("data")),
        "HORARIO": _format_appointment_time(schedule.get("horaInicio")),
    }


def _build_session_metadata(schedule: dict, phone: str) -> dict[str, str]:
    return {
        "appointment_id": str(schedule.get("id") or ""),
        "patient_name": str(schedule.get("nome", "Paciente")),
        "patient_phone": phone,
        "appointment_date": str(schedule.get("data") or ""),
        "appointment_time": str(schedule.get("horaInicio") or ""),
        "professional_name": str((schedule.get("profissionalSaude") or {}).get("nome") or ""),
    }


async def _dispatch_confirmations(schedules: list, delay_seconds: int):
    """Processa a fila de envios em lotes de template com atraso configurado entre lotes."""
    total = len(schedules)
    logger.info("[DISPATCH] Iniciando fila | total=%d | delay=%ds", total, delay_seconds)

    try:
        db = await get_supabase()
        settings = get_settings()
        channel_id = settings.wts_confirmation_channel_id
        template_id = settings.wts_confirmation_template_id

        if not channel_id:
            logger.error("[DISPATCH] WTS_CONFIRMATION_CHANNEL_ID não configurado — abortando fila")
            return
        if not template_id:
            logger.error("[DISPATCH] WTS_CONFIRMATION_TEMPLATE_ID não configurado — abortando fila")
            return

        sent_count = 0
        skipped_count = 0
        failed_count = 0
        pending_items: list[dict] = []

        for idx, sched in enumerate(schedules, start=1):
            appointment_id = sched.get("id")
            phone = normalize_brazil_phone(sched.get("telefonePrincipal"))
            if not phone:
                skipped_count += 1
                logger.info("[DISPATCH] %d/%d pulado (sem telefone) | appointment_id=%s", idx, total, appointment_id)
                continue

            try:
                existing = await db.table("schedule_confirmations").select("id, status").eq("appointment_id", appointment_id).execute()
                if existing.data and existing.data[0]["status"] != "failed":
                    skipped_count += 1
                    logger.info("[DISPATCH] %d/%d pulado (status=%s) | appointment_id=%s", idx, total, existing.data[0]["status"], appointment_id)
                    continue

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

                pending_items.append({
                    "appointment_id": str(appointment_id),
                    "confirmation_id": conf_id,
                    "message": {
                        "to": phone,
                        "senderId": str(appointment_id),
                        "parameters": _build_template_parameters(sched),
                        "sessionMetadata": _build_session_metadata(sched, phone),
                        **({"callbackUrl": settings.wts_confirmation_callback_url} if settings.wts_confirmation_callback_url else {}),
                    },
                })
                logger.info("[DISPATCH] %d/%d pronto para lote | appointment_id=%s | phone=%s", idx, total, appointment_id, phone)
            except Exception as e:
                failed_count += 1
                logger.error("[DISPATCH] %d/%d erro na preparação | appointment_id=%s | erro=%s", idx, total, appointment_id, e, exc_info=True)

        batches = _chunk_list(pending_items, 100)
        for batch_idx, batch in enumerate(batches, start=1):
            logger.info("[DISPATCH] Enviando lote %d/%d | tamanho=%d", batch_idx, len(batches), len(batch))
            try:
                results = await send_confirmation_template_batch([item["message"] for item in batch])
                results_by_sender = {
                    str(result.get("senderId") or ""): result
                    for result in results
                    if result.get("senderId")
                }

                for item in batch:
                    appointment_id = item["appointment_id"]
                    conf_id = item["confirmation_id"]
                    result = results_by_sender.get(appointment_id)

                    if not result:
                        failed_count += 1
                        logger.error("[DISPATCH] Resultado ausente no lote | appointment_id=%s", appointment_id)
                        await db.table("schedule_confirmations").update({"status": "failed"}).eq("id", conf_id).execute()
                        continue

                    remote_status = (result.get("status") or "").upper()
                    local_status = "failed" if remote_status == "FAILED" else "sent"
                    update_fields = {
                        "status": local_status,
                        "message_id": result.get("id"),
                    }
                    session_id = result.get("sessionId")
                    if session_id:
                        update_fields["session_id"] = session_id
                        update_fields["helena_session_id"] = session_id

                    await db.table("schedule_confirmations").update(update_fields).eq("id", conf_id).execute()

                    if local_status == "sent":
                        sent_count += 1
                        logger.info(
                            "[DISPATCH] Lote %d/%d enviado | appointment_id=%s | msg_id=%s | session_id=%s | remote_status=%s",
                            batch_idx,
                            len(batches),
                            appointment_id,
                            result.get("id"),
                            session_id,
                            remote_status,
                        )
                    else:
                        failed_count += 1
                        logger.error(
                            "[DISPATCH] Lote %d/%d falhou | appointment_id=%s | motivo=%s",
                            batch_idx,
                            len(batches),
                            appointment_id,
                            result.get("failedReason"),
                        )
            except Exception as e:
                failed_count += len(batch)
                logger.error("[DISPATCH] Falha no envio do lote %d/%d | erro=%s", batch_idx, len(batches), e, exc_info=True)
                for item in batch:
                    await db.table("schedule_confirmations").update({"status": "failed"}).eq("id", item["confirmation_id"]).execute()

            if batch_idx < len(batches) and delay_seconds > 0:
                await asyncio.sleep(delay_seconds)

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
            target = (clinic_now() + timedelta(days=1)).strftime("%Y-%m-%d")
            
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
            phone = normalize_brazil_phone(sched.get("telefonePrincipal"))
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
