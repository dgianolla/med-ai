import json
import logging
from anthropic import AsyncAnthropic

from config import get_settings
from db.models import SessionContext, AgentResult, HandoffPayload
from agents.base_agent import BaseAgent
from agents.handoff_utils import (
    DONE_PHRASES,
    SCHEDULING_HANDOFF_PHRASES,
    matches_any_phrase,
)
from agents.prompt_loader import load_prompt
from campaigns.service import get_campaign_service
from prompts.composer import (
    compose_agent_system,
    extract_and_strip_conflicts,
    format_campaign_block,
    format_campaigns_index,
    format_session_state,
)
from knowledge.tools import TOOLS as KNOWLEDGE_TOOLS, get_clinic_info
from knowledge.service import get_knowledge
from tools.campaign_tools import (
    TOOLS as CAMPAIGN_TOOLS,
    CAMPAIGN_TOOL_NAMES,
    execute_campaign_tool,
)
from services.priority_leads import has_endocrino_availability, create_priority_lead
from time_utils import clinic_now

logger = logging.getLogger(__name__)

ENDOCRINO_AVAILABILITY_WINDOW_DAYS = 5

PRIORITY_QUEUE_MESSAGE = (
    "Por conta da alta procura por esse tratamento, nossa equipe comercial vai "
    "entrar em contato com você o quanto antes para confirmar os melhores horários "
    "e te dar todas as orientações. Pode aguardar nosso retorno."
)

ALL_TOOLS = KNOWLEDGE_TOOLS + CAMPAIGN_TOOLS

_INTEREST_KEYWORDS = {
    "ozempic": ["ozempic", "semaglutida"],
    "mounjaro": ["mounjaro", "tirzepatida"],
}

_OBJECTION_KEYWORDS = {
    "preço": ["caro", "preço", "preco", "valor", "dinheiro", "parcel", "barato"],
    "medo": ["efeito colateral", "seguro", "risco", "medo", "preocupa"],
    "pensar": ["vou pensar", "depois", "talvez", "mais tarde"],
}


def _knowledge_facts() -> list[str]:
    """Snapshot dinâmico de pagamento para L5."""
    knowledge = get_knowledge()
    facts: list[str] = []

    payment = knowledge.get("clinic_info", "payment")
    if payment:
        installments = payment.get("installments", {})
        facts.append(
            f"pagamento: métodos={', '.join(payment.get('methods', []))} | "
            f"PIX={payment.get('pix_key', 'N/A')} | "
            f"exames/protocolos até {installments.get('exames_combos', '10x')} sem juros"
        )

    return facts


def _lead_facts(ctx: SessionContext) -> list[str]:
    """Fatos do lead (caneta_interesse, objeção, etc) para L5."""
    if not ctx.patient_metadata:
        return []
    facts: list[str] = []
    for k in ("caneta_interesse", "ja_usou_caneta", "objection", "ready_for_consult"):
        val = ctx.patient_metadata.get(k)
        if val:
            facts.append(f"{k}: {val}")
    return facts


class WeightLossAgent(BaseAgent):
    """
    Agente dedicado a leads do protocolo de canetas injetáveis (Ozempic / Mounjaro).
    Qualifica o lead, esclarece com transparência, derruba objeção e converte
    para consulta com endocrinologista (Dr. Arthur Wagner).
    """

    agent_type = "weight_loss"
    model = "claude-haiku-4-5"

    async def run(self, ctx: SessionContext) -> AgentResult:
        settings = get_settings()
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        patient_name = (ctx.patient_metadata or {}).get("name", "Desconhecido")
        logger.info("[WEIGHT_LOSS] Iniciando | patient=%s (%s)", patient_name, ctx.patient_phone)

        now = clinic_now()
        core_identity = load_prompt("weight_loss").format(today=now.strftime("%Y-%m-%d"))

        service = get_campaign_service()

        campaign_block = ""
        campaign_id = None
        if ctx.handoff_payload and ctx.handoff_payload.context:
            campaign_name = ctx.handoff_payload.context.get("campaign_name")
            if campaign_name:
                campaign = service.get(campaign_name)
                if campaign:
                    campaign_block = format_campaign_block(campaign)
                    campaign_id = campaign.campaign_id

        extra_facts = _knowledge_facts() + _lead_facts(ctx)
        session_metadata = format_session_state(ctx, extra_facts=extra_facts)

        system, trace = compose_agent_system(
            safety=load_prompt("_safety"),
            core_identity=core_identity,
            business_rules=load_prompt("_business_rules"),
            campaigns_index=format_campaigns_index(service),
            campaign_block=campaign_block,
            session_metadata=session_metadata,
        )
        logger.info(
            "[WEIGHT_LOSS] Trace | patient=%s | layers=%s | campaign_id=%s",
            patient_name, trace["layers_present"], campaign_id,
        )

        messages = self._build_history(ctx)

        reply = None
        for _ in range(5):
            response = await client.messages.create(
                model=self.model,
                max_tokens=384,
                temperature=0.7,
                system=system,
                tools=ALL_TOOLS,
                messages=messages,
            )

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    if block.name in CAMPAIGN_TOOL_NAMES:
                        result = execute_campaign_tool(block.name, block.input)
                    elif block.name == "get_clinic_info":
                        result = await get_clinic_info(block.input["query"])
                    else:
                        result = {"error": f"Tool desconhecida: {block.name}"}
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })

                messages.append({"role": "user", "content": tool_results})
                continue

            reply = next((b.text for b in response.content if hasattr(b, "text")), None)
            break

        reply, conflicts = extract_and_strip_conflicts(reply)
        if conflicts:
            logger.warning(
                "[WEIGHT_LOSS] Conflict | patient=%s | conflicts=%s",
                patient_name, conflicts,
            )

        last_user_msg = next(
            (m["content"] for m in reversed(ctx.conversation_history) if m.get("role") == "user"),
            "",
        ).lower()

        session_updates: dict = {"interest": "canetas"}
        for caneta, kws in _INTEREST_KEYWORDS.items():
            if any(kw in last_user_msg for kw in kws):
                session_updates["caneta_interesse"] = caneta
                break
        for objection, kws in _OBJECTION_KEYWORDS.items():
            if any(kw in last_user_msg for kw in kws):
                session_updates["objection"] = objection
                break

        handoff_target = None
        handoff_payload = None
        done = False

        if reply:
            if matches_any_phrase(reply, SCHEDULING_HANDOFF_PHRASES):
                has_slot = await has_endocrino_availability(ENDOCRINO_AVAILABILITY_WINDOW_DAYS)
                logger.info(
                    "[WEIGHT_LOSS] Checagem de agenda do endócrino | patient=%s | tem_vaga=%s",
                    patient_name, has_slot,
                )

                if has_slot:
                    handoff_target = "scheduling"
                    handoff_payload = HandoffPayload(
                        type="to_scheduling",
                        patient_name=(ctx.patient_metadata or {}).get("name"),
                        reason="Lead de canetas injetáveis encaminhado para consulta com endocrinologista",
                        specialty_needed="Endocrinologia e Metabologia",
                        context={
                            "specialty": "Endocrinologia e Metabologia",
                            "professional_id": 30319,
                            "professional_name": "Dr. Arthur Wagner",
                            "esp_id": 19,
                            "lead_source": "weight_loss",
                            "interest": "canetas",
                            **{k: v for k, v in session_updates.items() if v},
                            **((ctx.handoff_payload.context if ctx.handoff_payload and ctx.handoff_payload.context else {})),
                        },
                    )
                    reply = None
                    session_updates["ready_for_consult"] = "sim"
                    logger.info("[WEIGHT_LOSS] Handoff → scheduling (endócrino) | patient=%s", patient_name)
                else:
                    notes_parts = []
                    if session_updates.get("caneta_interesse"):
                        notes_parts.append(f"Interesse: {session_updates['caneta_interesse']}")
                    if session_updates.get("objection"):
                        notes_parts.append(f"Objeção: {session_updates['objection']}")
                    if last_user_msg:
                        notes_parts.append(f"Última msg: {last_user_msg[:200]}")

                    await create_priority_lead(
                        patient_id=ctx.patient_id,
                        session_id=ctx.session_id,
                        patient_name=(ctx.patient_metadata or {}).get("name") or patient_name,
                        patient_phone=ctx.patient_phone,
                        interest="canetas",
                        specialty="Endocrinologia e Metabologia",
                        source_agent="weight_loss",
                        caneta_preferida=session_updates.get("caneta_interesse"),
                        professional_id=30319,
                        professional_name="Dr. Arthur Wagner",
                        notes=" | ".join(notes_parts) if notes_parts else None,
                        conversation_history=ctx.conversation_history,
                        metadata={
                            "ready_for_consult": "encaixe",
                            "objection": session_updates.get("objection"),
                        },
                    )

                    reply = PRIORITY_QUEUE_MESSAGE
                    session_updates["ready_for_consult"] = "encaixe"
                    session_updates["status"] = "priority_queue"
                    done = True
                    logger.info(
                        "[WEIGHT_LOSS] Lead → fila de encaixe prioritário | patient=%s",
                        patient_name,
                    )
            elif matches_any_phrase(reply, DONE_PHRASES):
                done = True
                logger.info("[WEIGHT_LOSS] Sessão encerrada | patient=%s", patient_name)

        logger.info(
            "[WEIGHT_LOSS] Resposta | patient=%s | handoff=%s | done=%s | meta=%s",
            patient_name, handoff_target or "Nenhum", done, session_updates,
        )

        return AgentResult(
            reply=reply or None,
            handoff_target=handoff_target,
            handoff_payload=handoff_payload,
            session_updates=session_updates,
            done=done,
        )
