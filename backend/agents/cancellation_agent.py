import json
import logging
from anthropic import AsyncAnthropic

from config import get_settings
from db.models import SessionContext, AgentResult
from agents.base_agent import BaseAgent
from agents.prompt_loader import load_prompt
from campaigns.service import get_campaign_service
from prompts.composer import (
    compose_agent_system,
    extract_and_strip_conflicts,
    format_campaign_block,
    format_campaigns_index,
    format_session_state,
)
from tools.cancellation_tools import TOOLS
from tools.campaign_tools import (
    TOOLS as CAMPAIGN_TOOLS,
    CAMPAIGN_TOOL_NAMES,
    execute_campaign_tool,
)
from knowledge.tools import TOOLS as KNOWLEDGE_TOOLS
from integrations.scheduling_api import cancel_appointment
from time_utils import clinic_now

logger = logging.getLogger(__name__)

ALL_TOOLS = TOOLS + KNOWLEDGE_TOOLS + CAMPAIGN_TOOLS


class CancellationAgent(BaseAgent):
    agent_type = "cancellation"
    model = "claude-haiku-4-5"

    async def run(self, ctx: SessionContext) -> AgentResult:
        settings = get_settings()
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        patient_name = (ctx.patient_metadata or {}).get("name", "Desconhecido")
        logger.info("[CANCELLATION] Iniciando | patient=%s (%s)", patient_name, ctx.patient_phone)

        now = clinic_now()
        core_identity = load_prompt("cancellation").format(
            today=now.strftime("%Y-%m-%d"),
            month=now.strftime("%m"),
            year=now.strftime("%Y"),
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

        session_metadata = format_session_state(ctx)

        system, trace = compose_agent_system(
            safety=load_prompt("_safety"),
            core_identity=core_identity,
            business_rules=load_prompt("_business_rules"),
            campaigns_index=format_campaigns_index(service),
            campaign_block=campaign_block,
            session_metadata=session_metadata,
        )
        logger.info(
            "[CANCELLATION] Trace | patient=%s | layers=%s | campaign_id=%s",
            patient_name, trace["layers_present"], campaign_id,
        )

        messages = self._build_history(ctx)

        for _ in range(10):
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

                    result = await self._execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })

                    if block.name == "cancel_appointment" and result.get("success"):
                        ctx.patient_metadata = ctx.patient_metadata or {}
                        ctx.patient_metadata["cancelled"] = True
                        ctx.patient_metadata["cancelled_at"] = clinic_now().isoformat()
                        ctx.patient_metadata["cancel_reason"] = block.input.get("reason", "Não informado")

                messages.append({"role": "user", "content": tool_results})
                continue

            reply = next(
                (b.text for b in response.content if hasattr(b, "text")),
                None,
            )

            reply, conflicts = extract_and_strip_conflicts(reply)
            if conflicts:
                logger.warning(
                    "[CANCELLATION] Conflict | patient=%s | conflicts=%s",
                    patient_name, conflicts,
                )

            done = (
                reply is not None and
                any(word in reply.lower() for word in [
                    "cancelamento confirmado", "agendamento cancelado", "cancelado com sucesso",
                    "seu agendamento foi cancelado", "cancelamento realizado",
                    "qualquer dúvida", "tenha um ótimo dia", "até logo",
                ])
            )

            logger.info(
                "[CANCELLATION] Resposta | patient=%s | reply=%s | done=%s",
                patient_name, (reply or "")[:80], done,
            )

            return AgentResult(
                reply=reply or None,
                session_updates=ctx.patient_metadata,
                done=done,
            )

        return AgentResult(
            reply="Desculpe, tive um problema ao processar sua solicitação. Por favor, tente novamente.",
        )

    async def _execute_tool(self, tool_name: str, tool_input: dict) -> dict:
        try:
            if tool_name in CAMPAIGN_TOOL_NAMES:
                return execute_campaign_tool(tool_name, tool_input)

            if tool_name == "cancel_appointment":
                appointment_id = tool_input["appointment_id"]
                reason = tool_input.get("reason", "Solicitado pelo paciente via WhatsApp")

                logger.info(
                    "[CANCELLATION] Executando cancelamento | appointment_id=%d | reason=%s",
                    appointment_id, reason,
                )

                result = await cancel_appointment(appointment_id, reason)
                return {"success": True, "result": result, "appointment_id": appointment_id}

            elif tool_name == "get_clinic_info":
                from knowledge.service import get_knowledge
                knowledge = get_knowledge()
                return {"result": knowledge.search(tool_input["query"]), "query": tool_input["query"]}

        except Exception as e:
            logger.error("Erro na tool %s: %s", tool_name, e)
            return {"success": False, "error": str(e)}
