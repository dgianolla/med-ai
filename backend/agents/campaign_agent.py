import json
import logging

from anthropic import AsyncAnthropic

from agents.base_agent import BaseAgent
from agents.handoff_utils import (
    DONE_PHRASES,
    SCHEDULING_HANDOFF_PHRASES,
    build_combo_scheduling_handoff,
    build_consultation_scheduling_handoff,
    matches_any_phrase,
    set_combo_flow,
    set_consultation_flow,
)
from agents.prompt_loader import load_prompt
from campaigns.service import get_campaign_service
from config import get_settings
from db.models import AgentResult, HandoffPayload, SessionContext
from knowledge.tools import TOOLS as KNOWLEDGE_TOOLS, get_clinic_info
from prompts.composer import (
    compose_agent_system,
    extract_and_strip_conflicts,
    format_campaign_block,
    format_campaigns_index,
    format_session_state,
)
from tools.commercial_tools import TOOLS as COMMERCIAL_TOOLS, confirm_combo
from tools.campaign_tools import (
    TOOLS as CAMPAIGN_TOOLS,
    CAMPAIGN_TOOL_NAMES,
    execute_campaign_tool,
)

logger = logging.getLogger(__name__)

ALL_TOOLS = KNOWLEDGE_TOOLS + COMMERCIAL_TOOLS + CAMPAIGN_TOOLS

class CampaignAgent(BaseAgent):
    agent_type = "campaign"
    model = "claude-haiku-4-5"

    async def run(self, ctx: SessionContext) -> AgentResult:
        settings = get_settings()
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        patient_name = (ctx.patient_metadata or {}).get("name", "Desconhecido")
        logger.info("[CAMPAIGN] Iniciando | patient=%s (%s)", patient_name, ctx.patient_phone)

        campaign_name = None
        if ctx.handoff_payload and ctx.handoff_payload.context:
            campaign_name = ctx.handoff_payload.context.get("campaign_name")

        service = get_campaign_service()
        campaign = service.get(campaign_name) if campaign_name else None

        if not campaign:
            logger.warning(
                "[CAMPAIGN] Campanha não encontrada | requested=%s | patient=%s",
                campaign_name, patient_name,
            )
            return AgentResult(
                handoff_target="commercial",
                handoff_payload=HandoffPayload(
                    type="to_commercial",
                    patient_name=(ctx.patient_metadata or {}).get("name"),
                    reason="Campanha não encontrada ou não está mais ativa; seguir no comercial genérico",
                    context={
                        "previous_agent": "campaign",
                        "campaign_name": campaign_name,
                        "invisible_handoff": True,
                        **(
                            ctx.handoff_payload.context
                            if ctx.handoff_payload and ctx.handoff_payload.context
                            else {}
                        ),
                    },
                ),
            )

        logger.info(
            "[CAMPAIGN] Context | patient=%s | campaign_id=%s | campaign=%s | especialidade=%s | history=%s",
            patient_name,
            campaign.campaign_id,
            campaign.nome,
            campaign.especialidade or "-",
            len(ctx.conversation_history),
        )

        # Montagem do system prompt em camadas L1..L5 com meta-regra de precedência.
        system, trace = compose_agent_system(
            safety=load_prompt("_safety"),
            core_identity=load_prompt("campaign"),
            business_rules=load_prompt("_business_rules"),
            campaigns_index=format_campaigns_index(service),
            campaign_block=format_campaign_block(campaign),
            session_metadata=format_session_state(ctx),
        )

        logger.info(
            "[CAMPAIGN] Trace | patient=%s | campaign_id=%s | layers=%s | layer_chars=%s",
            patient_name,
            campaign.campaign_id,
            trace["layers_present"],
            trace["layers_total_chars"],
        )

        messages = self._build_history(ctx)

        reply = None
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
                                "[CAMPAIGN] Combo confirmado | patient=%s | campaign=%s | combo=%s | specialty=%s",
                                patient_name,
                                campaign.nome,
                                result["combo_id"],
                                result.get("consultation_specialty"),
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

            reply = next((b.text for b in response.content if hasattr(b, "text")), None)
            break

        # Extrai e remove marcações [[conflict: ...]] auto-reportadas pelo modelo.
        reply, conflicts = extract_and_strip_conflicts(reply)
        if conflicts:
            logger.warning(
                "[CAMPAIGN] Conflict | patient=%s | campaign_id=%s | conflicts=%s",
                patient_name, campaign.campaign_id, conflicts,
            )

        handoff_target = None
        handoff_payload = None
        done = False

        if confirmed_combo and confirmed_combo.get("consultation_included"):
            set_combo_flow(ctx, confirmed_combo["combo_id"])

            handoff_target = "scheduling"
            handoff_payload = build_combo_scheduling_handoff(
                ctx,
                patient_name=(ctx.patient_metadata or {}).get("name"),
                reason=(
                    f"Paciente confirmou o combo {confirmed_combo['name']} "
                    f"na campanha {campaign.nome} — etapa de consulta "
                    f"({confirmed_combo['consultation_specialty']})"
                ),
                source_agent="campaign",
                combo=confirmed_combo,
                extra_context={
                    "campaign_name": campaign.nome,
                    "lead_source": "campaign",
                },
            )
            reply = None
            logger.info(
                "[CAMPAIGN] Handoff | kind=invisivel | from=campaign | to=scheduling | patient=%s | campaign=%s | combo=%s | specialty=%s",
                patient_name,
                campaign.nome,
                confirmed_combo["combo_id"],
                confirmed_combo["consultation_specialty"],
            )
        elif reply:
            if matches_any_phrase(reply, SCHEDULING_HANDOFF_PHRASES):
                set_consultation_flow(ctx)
                handoff_payload = build_consultation_scheduling_handoff(
                    ctx,
                    patient_name=(ctx.patient_metadata or {}).get("name"),
                    reason=f"Paciente avançou na campanha {campaign.nome} e quer agendar",
                    source_agent="campaign",
                    specialty_needed=campaign.especialidade,
                    extra_context={
                        "campaign_name": campaign.nome,
                        "lead_source": "campaign",
                    },
                )
                handoff_context = {
                    "campaign_name": campaign.nome,
                    "lead_source": "campaign",
                    **(handoff_payload.context or {}),
                }
                if campaign.especialidade:
                    handoff_context["specialty"] = campaign.especialidade
                handoff_payload.context = handoff_context

                handoff_target = "scheduling"
                # O handoff para agendamento é interno: o paciente deve receber
                # a próxima mensagem já do fluxo de agenda, sem "te encaminhar".
                reply = None
                logger.info(
                    "[CAMPAIGN] Handoff | kind=invisivel | from=campaign | to=scheduling | patient=%s | campaign=%s | specialty=%s",
                    patient_name, campaign.nome, campaign.especialidade,
                )
            elif matches_any_phrase(reply, DONE_PHRASES):
                done = True
                logger.info("[CAMPAIGN] Sessão encerrada | patient=%s | campaign=%s", patient_name, campaign.nome)

        logger.info(
            "[CAMPAIGN] Result | patient=%s | campaign=%s | handoff=%s | flow=%s/%s | combo=%s | done=%s | replied=%s",
            patient_name,
            campaign.nome,
            handoff_target or "Nenhum",
            ctx.flow_type,
            ctx.flow_stage,
            ctx.combo_id,
            done,
            bool(reply),
        )

        return AgentResult(
            reply=reply,
            handoff_target=handoff_target,
            handoff_payload=handoff_payload,
            done=done,
        )
