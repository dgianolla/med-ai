import logging
from datetime import datetime, timezone

from db.models import IncomingMessage, AgentResult, SessionContext
from db.client import get_supabase
from orchestrator.session_manager import get_session_manager
from integrations.whatsapp import get_whatsapp_client

logger = logging.getLogger(__name__)


async def _persist_message(
    session_id: str,
    wts_message_id: str,
    agent_id: str,
    role: str,
    message_type: str,
    content: str,
    file_url: str | None = None,
) -> None:
    """Salva mensagem no Supabase de forma não-bloqueante."""
    try:
        db = await get_supabase()
        await db.table("messages").insert({
            "session_id": session_id,
            "wts_message_id": wts_message_id or None,
            "agent_id": agent_id,
            "role": role,
            "message_type": message_type,
            "content": content,
            "file_url": file_url,
        }).execute()
    except Exception as e:
        logger.error("Erro ao persistir mensagem: %s", e)


async def _persist_session(ctx: SessionContext) -> None:
    """Upsert da sessão no Supabase."""
    try:
        db = await get_supabase()
        await db.table("sessions").upsert({
            "id": ctx.session_id,
            "wts_session_id": ctx.wts_session_id,
            "current_agent": ctx.current_agent,
            "status": "active",
            "handoff_payload": ctx.handoff_payload.model_dump() if ctx.handoff_payload else None,
            "last_message_preview": (ctx.conversation_history[-1]["content"][:100]
                                     if ctx.conversation_history else None),
            "last_activity_at": ctx.last_activity_at.isoformat(),
        }).execute()
    except Exception as e:
        logger.error("Erro ao persistir sessão: %s", e)


async def _ensure_patient(ctx: SessionContext, incoming: IncomingMessage) -> str | None:
    """Garante que o paciente existe no Supabase. Retorna patient_id."""
    try:
        db = await get_supabase()
        result = await db.table("patients").select("id").eq("phone", incoming.patient_phone).execute()

        if result.data:
            return result.data[0]["id"]

        # Cria paciente novo
        insert = await db.table("patients").insert({
            "phone": incoming.patient_phone,
            "wts_contact_id": incoming.wts_contact_id or None,
            "name": incoming.patient_name,
        }).execute()
        return insert.data[0]["id"] if insert.data else None
    except Exception as e:
        logger.error("Erro ao garantir paciente: %s", e)
        return None


async def dispatch(incoming: IncomingMessage) -> None:
    """
    Loop central de orquestração.
    1. Carrega ou cria sessão
    2. Appenda mensagem ao histórico
    3. Seleciona e executa o agente correto
    4. Envia resposta ao paciente (se houver)
    5. Trata handoff para próximo agente
    6. Persiste tudo
    """
    sm = get_session_manager()
    whatsapp = get_whatsapp_client()

    # 1. Sessão
    ctx, is_new = await sm.get_or_create(
        patient_phone=incoming.patient_phone,
        wts_session_id=incoming.wts_session_id,
        patient_name=incoming.patient_name,
    )

    # 2. Garante paciente no Supabase
    await _ensure_patient(ctx, incoming)

    # 3. Garante sessão no Supabase ANTES de inserir mensagens (FK constraint)
    await _persist_session(ctx)

    # 4. Appenda mensagem do paciente ao histórico
    sm.append_message(ctx, "user", incoming.text)

    # Persiste mensagem do paciente
    await _persist_message(
        session_id=ctx.session_id,
        wts_message_id=incoming.wts_message_id,
        agent_id="user",
        role="user",
        message_type=incoming.message_type,
        content=incoming.text,
        file_url=incoming.file_url,
    )

    # Se mensagem tem mídia (imagem/PDF), salva file_url no contexto para o agente de Exames
    if incoming.message_type in ("image", "pdf", "file") and incoming.file_url:
        ctx.exam_content = incoming.file_url

    # 4. Loop de dispatch (permite handoffs imediatos sem nova mensagem do paciente)
    max_hops = 5  # evita loop infinito
    for _ in range(max_hops):
        agent_id = ctx.current_agent
        logger.info("Despachando | session=%s | agent=%s", ctx.session_id, agent_id)

        result = await _run_agent(agent_id, ctx)

        # Appenda resposta do agente ao histórico
        if result.reply:
            sm.append_message(ctx, "assistant", result.reply)
            await _persist_message(
                session_id=ctx.session_id,
                wts_message_id=None,
                agent_id=agent_id,
                role="assistant",
                message_type="text",
                content=result.reply,
            )

            # Envia ao paciente via wts.chat
            try:
                await whatsapp.send_text(
                    session_id=ctx.wts_session_id,
                    text=result.reply,
                    ref_id=incoming.wts_message_id,
                )
            except Exception as e:
                logger.error("Erro ao enviar mensagem via wts.chat: %s", e)

        # Atualiza metadata se o agente coletou dados
        if result.session_updates:
            sm.update_patient_metadata(ctx, result.session_updates)

        # Sessão concluída
        if result.done:
            ctx.current_agent = "triage"  # reset para próxima interação
            await sm.save(ctx)
            await _finish_session(ctx.session_id)
            break

        # Handoff para próximo agente
        if result.handoff_target and result.handoff_target != agent_id:
            sm.set_agent(ctx, result.handoff_target, result.handoff_payload)
            await _persist_session(ctx)
            await sm.save(ctx)

            # Aplica etiqueta do novo agente e salva nota com intenção do paciente
            from integrations.whatsapp.wts_client import AGENT_TAG_NAMES
            tag_name = AGENT_TAG_NAMES.get(result.handoff_target)
            if tag_name:
                await whatsapp.apply_tag(ctx.wts_session_id, tag_name)

            if result.handoff_payload and result.handoff_payload.reason:
                patient_name = (ctx.patient_metadata or {}).get("name", "Paciente")
                note = f"[LIA] {patient_name} → {tag_name or result.handoff_target}\nIntenção: {result.handoff_payload.reason}"
                await whatsapp.add_note(ctx.wts_session_id, note)

            # Se o próximo agente não precisa de mais input do paciente (ex: Triagem → Agendamento),
            # continua o loop imediatamente
            if agent_id == "triage":
                continue
            break

        # Agente terminou sem handoff — aguarda próxima mensagem do paciente
        await sm.save(ctx)
        await _persist_session(ctx)
        break

    else:
        logger.warning("Max hops atingido na sessão %s", ctx.session_id)
        await sm.save(ctx)


async def _run_agent(agent_id: str, ctx: SessionContext) -> AgentResult:
    """Instancia e executa o agente pelo ID."""
    # Import dinâmico — evita importação circular no topo
    if agent_id == "triage":
        from agents.triage_agent import TriageAgent
        return await TriageAgent().run(ctx)
    elif agent_id == "scheduling":
        from agents.scheduling_agent import SchedulingAgent
        return await SchedulingAgent().run(ctx)
    elif agent_id == "exams":
        from agents.exams_agent import ExamsAgent
        return await ExamsAgent().run(ctx)
    elif agent_id == "commercial":
        from agents.commercial_agent import CommercialAgent
        return await CommercialAgent().run(ctx)
    elif agent_id == "return":
        from agents.return_agent import ReturnAgent
        return await ReturnAgent().run(ctx)
    else:
        logger.error("Agente desconhecido: %s", agent_id)
        return AgentResult(reply="Desculpe, ocorreu um erro interno. Tente novamente.", done=True)


async def _finish_session(session_id: str) -> None:
    """Marca sessão como concluída no Supabase."""
    try:
        db = await get_supabase()
        await db.table("sessions").update({
            "status": "completed",
            "ended_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", session_id).execute()
    except Exception as e:
        logger.error("Erro ao finalizar sessão: %s", e)
