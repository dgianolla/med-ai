import json
import logging
from anthropic import AsyncAnthropic

from config import get_settings
from db.models import SessionContext, AgentResult, HandoffPayload
from agents.base_agent import BaseAgent
from agents.handoff_utils import (
    build_combo_scheduling_handoff,
    build_consultation_scheduling_handoff,
    set_combo_flow,
    set_consultation_flow,
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
from tools.commercial_tools import TOOLS as COMMERCIAL_TOOLS, confirm_combo
from tools.campaign_tools import (
    TOOLS as CAMPAIGN_TOOLS,
    CAMPAIGN_TOOL_NAMES,
    execute_campaign_tool,
)

logger = logging.getLogger(__name__)

ALL_TOOLS = KNOWLEDGE_TOOLS + COMMERCIAL_TOOLS + CAMPAIGN_TOOLS

_WEIGHT_LOSS_KEYWORDS = [
    "ozempic",
    "mounjaro",
    "semaglutida",
    "tirzepatida",
    "wegovy",
    "saxenda",
    "caneta",
    "canetas",
    "protocolo de emagrecimento",
    "emagrecimento",
]

_SCHEDULING_HANDOFF_PHRASES = [
    "vou te encaminhar para agendamento", "agente de agendamento",
    "equipe de agendamento", "vou te encaminhar para a agenda",
]

_DONE_PHRASES = [
    "até logo", "até mais", "obrigado por entrar em contato",
    "qualquer dúvida", "boa consulta", "tenha um ótimo dia",
]


def _knowledge_facts() -> list[str]:
    """Snapshot dinâmico de pagamento/endereço para L5."""
    knowledge = get_knowledge()
    facts: list[str] = []

    payment = knowledge.get("clinic_info", "payment")
    if payment:
        installments = payment.get("installments", {})
        facts.append(
            f"pagamento: métodos={', '.join(payment.get('methods', []))} | "
            f"PIX={payment.get('pix_key', 'N/A')} | "
            f"consultas até {installments.get('consultas', '2x')} | "
            f"exames/combos até {installments.get('exames_combos', '10x')}"
        )

    address = knowledge.get("clinic_info", "address")
    if address:
        facts.append(
            f"endereço: {address.get('street')} — {address.get('landmark')}"
        )

    return facts


class CommercialAgent(BaseAgent):
    agent_type = "commercial"
    model = "claude-haiku-4-5"

    async def run(self, ctx: SessionContext) -> AgentResult:
        settings = get_settings()
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        patient_name = (ctx.patient_metadata or {}).get("name", "Desconhecido")
        logger.info("[COMMERCIAL] Iniciando | patient=%s (%s)", patient_name, ctx.patient_phone)

        last_user_msg = next(
            (m["content"] for m in reversed(ctx.conversation_history) if m.get("role") == "user"),
            "",
        ).lower()

        if any(keyword in last_user_msg for keyword in _WEIGHT_LOSS_KEYWORDS):
            logger.info(
                "[COMMERCIAL] Handoff invisível → weight_loss | patient=%s | msg=%s",
                patient_name,
                last_user_msg[:120],
            )
            return AgentResult(
                handoff_target="weight_loss",
                handoff_payload=HandoffPayload(
                    type="to_weight_loss",
                    patient_name=(ctx.patient_metadata or {}).get("name"),
                    reason="Lead sobre canetas/protocolo de emagrecimento recebido no comercial",
                    context={
                        "previous_agent": "commercial",
                        "lead_source": "commercial",
                        "interest": "canetas",
                        "invisible_handoff": True,
                        **(
                            ctx.handoff_payload.context
                            if ctx.handoff_payload and ctx.handoff_payload.context
                            else {}
                        ),
                    },
                ),
            )

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

        session_metadata = format_session_state(ctx, extra_facts=_knowledge_facts())

        system, trace = compose_agent_system(
            safety=load_prompt("_safety"),
            core_identity=load_prompt("commercial"),
            business_rules=load_prompt("_business_rules"),
            campaigns_index=format_campaigns_index(service),
            campaign_block=campaign_block,
            session_metadata=session_metadata,
        )
        logger.info(
            "[COMMERCIAL] Trace | patient=%s | layers=%s | campaign_id=%s",
            patient_name, trace["layers_present"], campaign_id,
        )

        messages = self._build_history(ctx)

        confirmed_combo: dict | None = None

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
                    elif block.name == "confirm_combo":
                        result = confirm_combo(block.input["combo_id"])
                        if result.get("ok"):
                            confirmed_combo = result
                            logger.info(
                                "[COMMERCIAL] Combo confirmado | patient=%s | combo=%s | specialty=%s",
                                patient_name, result["combo_id"], result.get("consultation_specialty"),
                            )
                    else:
                        result = {"error": f"Tool desconhecida: {block.name}"}

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })

                messages.append({"role": "user", "content": tool_results})
                continue

            reply = next(
                (b.text for b in response.content if hasattr(b, "text")),
                None,
            )
            break
        else:
            reply = None

        reply, conflicts = extract_and_strip_conflicts(reply)
        if conflicts:
            logger.warning(
                "[COMMERCIAL] Conflict | patient=%s | conflicts=%s",
                patient_name, conflicts,
            )

        handoff_target = None
        handoff_payload = None
        done = False

        if confirmed_combo and confirmed_combo.get("consultation_included"):
            set_combo_flow(ctx, confirmed_combo["combo_id"])

            handoff_target = "scheduling"
            handoff_payload = build_combo_scheduling_handoff(
                ctx,
                patient_name=patient_name,
                reason=f"Combo confirmado: {confirmed_combo['name']} — etapa de consulta ({confirmed_combo['consultation_specialty']})",
                source_agent="commercial",
                combo=confirmed_combo,
            )

        elif reply:
            reply_lower = reply.lower()
            if any(p in reply_lower for p in _SCHEDULING_HANDOFF_PHRASES):
                set_consultation_flow(ctx)
                handoff_target = "scheduling"
                handoff_payload = build_consultation_scheduling_handoff(
                    ctx,
                    patient_name=patient_name,
                    reason="Paciente quer agendar consulta após atendimento comercial",
                    source_agent="commercial",
                )
                logger.info("[COMMERCIAL] Handoff → scheduling | patient=%s", patient_name)
            elif any(p in reply_lower for p in _DONE_PHRASES):
                done = True
                logger.info("[COMMERCIAL] Sessão encerrada | patient=%s", patient_name)

        logger.info(
            "[COMMERCIAL] Resposta | patient=%s | handoff=%s | flow=%s/%s | combo=%s | done=%s",
            patient_name,
            handoff_target or "Nenhum",
            ctx.flow_type, ctx.flow_stage,
            ctx.combo_id,
            done,
        )

        return AgentResult(
            reply=reply or None,
            handoff_target=handoff_target,
            handoff_payload=handoff_payload,
            done=done,
        )
