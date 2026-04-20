import logging
from datetime import datetime, timezone
from typing import Sequence

from db.models import IncomingMessage, AgentResult, SessionContext
from db.client import get_supabase
from orchestrator.session_manager import get_session_manager
from orchestrator.router import should_handoff
from integrations.whatsapp import get_whatsapp_client
from services.message_buffer import BufferedMessageFragment

logger = logging.getLogger(__name__)


def _short(text: str | None, limit: int = 120) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _handoff_kind(result: AgentResult) -> str:
    context = result.handoff_payload.context if result.handoff_payload and result.handoff_payload.context else {}
    if context.get("human_handoff"):
        return "humano"
    if context.get("invisible_handoff") or context.get("auto_handoff_from_commercial"):
        return "invisivel"
    return "visivel"


def _is_human_handoff(result: AgentResult) -> bool:
    context = result.handoff_payload.context if result.handoff_payload and result.handoff_payload.context else {}
    return bool(context.get("human_handoff"))


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


def _apply_buffered_media(ctx: SessionContext, fragments: Sequence[BufferedMessageFragment]) -> None:
    file_urls = [
        fragment.file_url
        for fragment in fragments
        if fragment.message_type in ("image", "pdf", "file") and fragment.file_url
    ]
    if not file_urls:
        return

    existing = ctx.exam_content
    existing_urls = existing if isinstance(existing, list) else ([existing] if existing else [])
    ctx.exam_content = existing_urls + file_urls


async def _persist_session(ctx: SessionContext) -> None:
    """Upsert da sessão no Supabase."""
    try:
        db = await get_supabase()
        await db.table("sessions").upsert({
            "id": ctx.session_id,
            "patient_id": ctx.patient_id,
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
    """Garante que o paciente existe no Supabase. Retorna patient_id e vincula ao contexto."""
    try:
        db = await get_supabase()
        result = await db.table("patients").select("id").eq("phone", incoming.patient_phone).execute()

        if result.data:
            patient_id = result.data[0]["id"]
        else:
            # Cria paciente novo
            insert = await db.table("patients").insert({
                "phone": incoming.patient_phone,
                "wts_contact_id": incoming.wts_contact_id or None,
                "name": incoming.patient_name,
            }).execute()
            patient_id = insert.data[0]["id"] if insert.data else None

        # Vincula patient_id ao contexto da sessão
        if patient_id:
            ctx.patient_id = patient_id

        return patient_id
    except Exception as e:
        logger.error("Erro ao garantir paciente: %s", e)
        return None


async def dispatch(
    incoming: IncomingMessage,
    buffered_fragments: Sequence[BufferedMessageFragment] | None = None,
) -> None:
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
    logger.info(
        "📩 MENSAGEM RECEBIDA | session=%s | patient=%s | phone=%s | new=%s | current_agent=%s | type=%s | text=%s",
        ctx.session_id,
        incoming.patient_name or (ctx.patient_metadata or {}).get("name", "Desconhecido"),
        incoming.patient_phone,
        is_new,
        ctx.current_agent,
        incoming.message_type,
        _short(incoming.text),
    )

    # 2. Garante paciente no Supabase
    await _ensure_patient(ctx, incoming)

    # 3. Garante sessão no Supabase ANTES de inserir mensagens (FK constraint)
    await _persist_session(ctx)

    # 4. Persiste fragmentos originais e adiciona apenas a versão consolidada ao histórico do agente
    if buffered_fragments:
        for fragment in buffered_fragments:
            await _persist_message(
                session_id=ctx.session_id,
                wts_message_id=fragment.wts_message_id,
                agent_id="user",
                role="user",
                message_type=fragment.message_type,
                content=fragment.text,
                file_url=fragment.file_url,
            )
        _apply_buffered_media(ctx, buffered_fragments)
    else:
        await _persist_message(
            session_id=ctx.session_id,
            wts_message_id=incoming.wts_message_id,
            agent_id="user",
            role="user",
            message_type=incoming.message_type,
            content=incoming.text,
            file_url=incoming.file_url,
        )
        _apply_buffered_media(
            ctx,
            [
                BufferedMessageFragment(
                    wts_message_id=incoming.wts_message_id,
                    message_type=incoming.message_type,
                    text=incoming.text,
                    file_url=incoming.file_url,
                    received_at=incoming.received_at,
                )
            ],
        )

    sm.append_message(ctx, "user", incoming.text)

    if ctx.flow_stage == "human_handoff":
        logger.info(
            "🧑‍💼 HUMANO ATIVO | session=%s | patient=%s | sem resposta automática",
            ctx.session_id,
            (ctx.patient_metadata or {}).get("name", "Desconhecido"),
        )
        await sm.save(ctx)
        await _persist_session(ctx)
        return

    # 3.5. Router inteligente: detecta se a mensagem pertence a outro agente
    target_agent = should_handoff(ctx.current_agent, incoming.text)
    if target_agent and target_agent != ctx.current_agent:
        previous = ctx.current_agent

        # Constrói handoff_payload com contexto acumulado
        from db.models import HandoffPayload
        payload = HandoffPayload(
            type=f"to_{target_agent}",
            patient_name=(ctx.patient_metadata or {}).get("name"),
            reason=f"Router: mensagem sobre '{incoming.text[:60]}' detectada como domínio de {target_agent}",
            context={
                "collected_by_router": True,
                "previous_agent": previous,
                **(ctx.handoff_payload.context if ctx.handoff_payload and ctx.handoff_payload.context else {}),
                **(ctx.patient_metadata or {}),
            },
        )

        sm.set_agent(ctx, target_agent, payload)
        patient_name = (ctx.patient_metadata or {}).get("name", "Desconhecido")
        logger.info(
            "🔀 ROUTER | from=%s | to=%s | patient=%s | text=%s",
            previous, target_agent, patient_name, _short(incoming.text),
        )

    # 4. Loop de dispatch (permite handoffs imediatos sem nova mensagem do paciente)
    max_hops = 5  # evita loop infinito
    previous_agent = None
    for hop in range(max_hops):
        agent_id = ctx.current_agent
        patient_name = (ctx.patient_metadata or {}).get("name", "Desconhecido")
        if hop == 0:
            logger.info(
                "▶️ DISPATCH | hop=%s | agent=%s | patient=%s | phone=%s | text=%s",
                hop,
                agent_id,
                patient_name,
                ctx.patient_phone,
                _short(incoming.text),
            )
        else:
            logger.info(
                "🔁 CONTINUANDO | hop=%s | from=%s | to=%s | patient=%s",
                hop,
                previous_agent,
                agent_id,
                patient_name,
            )

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

            logger.info(
                "💬 RESPOSTA | agent=%s | patient=%s | text=%s",
                agent_id, patient_name, _short(result.reply),
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
            logger.info(
                "✅ SESSÃO CONCLUÍDA | session=%s | agent=%s | patient=%s",
                ctx.session_id,
                agent_id, patient_name,
            )
            break

        # Handoff para próximo agente
        if result.handoff_target and result.handoff_target != agent_id:
            if _is_human_handoff(result):
                previous_agent = agent_id
                context = result.handoff_payload.context or {}
                ctx.flow_stage = "human_handoff"
                sm.set_agent(ctx, result.handoff_target, result.handoff_payload)
                await _persist_session(ctx)
                await sm.save(ctx)

                logger.info(
                    "🧑‍💼 HANDOFF HUMANO | from=%s | to=%s | patient=%s | reason=%s",
                    previous_agent,
                    result.handoff_target,
                    patient_name,
                    _short(result.handoff_payload.reason if result.handoff_payload else "N/A"),
                )

                tag_name = context.get("human_tag")
                if tag_name:
                    await whatsapp.apply_tag(ctx.wts_session_id, tag_name)

                note = context.get("human_note") or (result.handoff_payload.reason if result.handoff_payload else None)
                if note:
                    await whatsapp.add_note(ctx.wts_session_id, note)

                if context.get("human_complete_session"):
                    await whatsapp.complete_session(ctx.wts_session_id)

                break

            previous_agent = agent_id
            sm.set_agent(ctx, result.handoff_target, result.handoff_payload)
            await _persist_session(ctx)
            await sm.save(ctx)

            logger.info(
                "🔀 HANDOFF | kind=%s | from=%s | to=%s | patient=%s | reason=%s",
                _handoff_kind(result),
                previous_agent,
                result.handoff_target,
                patient_name,
                _short(result.handoff_payload.reason if result.handoff_payload else "N/A"),
            )

            # Verifica se é um handoff invisível entre agentes internos
            is_invisible_handoff = (
                result.handoff_payload
                and result.handoff_payload.context
                and (
                    result.handoff_payload.context.get("auto_handoff_from_commercial")
                    or result.handoff_payload.context.get("invisible_handoff")
                )
            )

            if not is_invisible_handoff:
                # Aplica etiqueta do novo agente e salva nota com intenção do paciente
                from integrations.whatsapp.wts_client import AGENT_TAG_NAMES
                tag_name = AGENT_TAG_NAMES.get(result.handoff_target)
                if tag_name:
                    await whatsapp.apply_tag(ctx.wts_session_id, tag_name)

                if result.handoff_payload and result.handoff_payload.reason:
                    patient_name = (ctx.patient_metadata or {}).get("name", "Paciente")
                    note = f"[LIA] {patient_name} → {tag_name or result.handoff_target}\nIntenção: {result.handoff_payload.reason}"
                    await whatsapp.add_note(ctx.wts_session_id, note)
            else:
                logger.info(
                    "🔒 HANDOFF INVISÍVEL | from=%s | to=%s | patient=%s | whatsapp_side_effects=off",
                    previous_agent, result.handoff_target, patient_name,
                )

            # Se o próximo agente não precisa de mais input do paciente (ex: Triagem → Agendamento),
            # continua o loop imediatamente
            if agent_id == "triage":
                continue
            # Handoffs invisíveis também continuam imediatamente
            if is_invisible_handoff:
                continue
            break

        # Agente terminou sem handoff — aguarda próxima mensagem do paciente
        logger.info(
            "⏸️ AGUARDANDO PACIENTE | session=%s | agent=%s | patient=%s",
            ctx.session_id,
            agent_id,
            patient_name,
        )
        await sm.save(ctx)
        await _persist_session(ctx)
        break

    else:
        logger.warning("⚠️ MAX_HOPS | session=%s | patient=%s | hops=%s", ctx.session_id, (ctx.patient_metadata or {}).get("name", "Desconhecido"), max_hops)
        await sm.save(ctx)


async def _run_agent(agent_id: str, ctx: SessionContext) -> AgentResult:
    """Instancia e executa o agente pelo ID."""
    import time
    start = time.time()
    patient_name = (ctx.patient_metadata or {}).get("name", "Desconhecido")
    logger.info("⚙️ AGENTE START | agent=%s | patient=%s | session=%s", agent_id, patient_name, ctx.session_id)

    # Import dinâmico — evita importação circular no topo
    if agent_id == "triage":
        from agents.triage_agent import TriageAgent
        result = await TriageAgent().run(ctx)
    elif agent_id == "scheduling":
        from agents.scheduling_agent import SchedulingAgent
        result = await SchedulingAgent().run(ctx)
    elif agent_id == "exams":
        from agents.exams_agent import ExamsAgent
        result = await ExamsAgent().run(ctx)
    elif agent_id == "commercial":
        from agents.commercial_agent import CommercialAgent
        result = await CommercialAgent().run(ctx)
    elif agent_id == "campaign":
        from agents.campaign_agent import CampaignAgent
        result = await CampaignAgent().run(ctx)
    elif agent_id == "return":
        from agents.return_agent import ReturnAgent
        result = await ReturnAgent().run(ctx)
    elif agent_id == "cancellation":
        from agents.cancellation_agent import CancellationAgent
        result = await CancellationAgent().run(ctx)
    elif agent_id == "weight_loss":
        from agents.weight_loss_agent import WeightLossAgent
        result = await WeightLossAgent().run(ctx)
    else:
        logger.error("Agente desconhecido: %s", agent_id)
        return AgentResult(reply="Desculpe, ocorreu um erro interno. Tente novamente.", done=True)

    elapsed = time.time() - start
    logger.info(
        "⏱️ AGENTE END | agent=%s | patient=%s | session=%s | elapsed=%.2fs | done=%s | handoff=%s | replied=%s",
        agent_id, patient_name, ctx.session_id, elapsed, result.done, result.handoff_target or "Nenhum", bool(result.reply),
    )
    return result


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
