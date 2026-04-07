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

async def _dispatch_confirmations(schedules: list, delay_seconds: int):
    """Processa a fila de envios com o atraso configurado."""
    db = get_supabase()
    wts_client = get_confirmation_whatsapp_client()
    
    # Pegar o ID do template no painel de configurações (fixo por enquanto como dummy ou busca ativa)
    # Suponha que já foi aprovado no wts.chat o template 'confirmacao_consulta'
    TEMPLATE_ID = "confirmacao_consulta_v1" # Alterar conforme setup no wts
    
    for sched in schedules:
        try:
            # Pula se o telefone for vazio
            phone = sched.get("telefonePrincipal", "").strip()
            if not phone:
                continue
                
            # Verifica se já existe para não enviar duplicado
            existing = db.table("schedule_confirmations").select("id, status").eq("appointment_id", sched["id"]).execute()
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
            res = db.table("schedule_confirmations").insert(data_insert).execute()
            conf_id = res.data[0]["id"]
            
            try:
                # Dispara template
                # Aqui o WTS precisa criar sessao, como nao temos endpoint create_session no client atual, 
                # assumimos que passamos o phone como session_id se nao instanciado, ou a api interna cria.
                # Como é um disparo ativo (nova regra), precisará ser ajustado se o wts_client 
                # exigir criacao de sessao explicita antes de `send_template`.
                msg_id = await wts_client.send_template(
                    session_id=phone, # Usando o telefone como referencia inicial
                    template_id=TEMPLATE_ID,
                    parameters={"patient_name": sched.get("nome", "Paciente")}
                )
                
                # Update success
                db.table("schedule_confirmations").update({
                    "status": "sent", 
                    "message_id": msg_id,
                    "session_id": phone # atualiza a sessao correta
                }).eq("id", conf_id).execute()
                
            except Exception as e:
                logger.error(f"Erro ao disparar WTS: {e}")
                db.table("schedule_confirmations").update({"status": "failed"}).eq("id", conf_id).execute()
            
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
        db = get_supabase()
        res = db.table("schedule_confirmations").select("*").eq("appointment_date", date).order("created_at", desc=True).execute()
        return {"confirmations": res.data or []}
    except Exception as e:
        logger.error(f"Erro ao listar confirmacoes: {e}")
        return {"confirmations": []}


@router.get("/api/schedules/preview")
async def preview_schedules(date: str):
    """Retorna todos os agendamentos da API mesclados com o status no Supabase."""
    try:
        # Busca da API AppHealth
        schedules = await get_agenda(date, date)
        
        # Busca status atuais no Supabase
        db = get_supabase()
        status_map = {}
        try:
            db_res = db.table("schedule_confirmations").select("appointment_id, status").eq("appointment_date", date).execute()
            status_map = {item["appointment_id"]: item["status"] for item in (db_res.data or [])}
        except Exception as e:
            logger.warning(f"Erro ao buscar status no BD (tabela pode nao existir): {e}")
        
        preview = []
        for sched in schedules:
            app_id = sched.get("id")
            phone = sched.get("telefonePrincipal", "")
            if not phone:
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
        return {"schedules": preview}
    except Exception as e:
        logger.error(f"Erro no preview de agenda: {e}")
        raise HTTPException(status_code=500, detail="Erro ao carregar preview da agenda")
