import json
import logging
from anthropic import AsyncAnthropic

from config import get_settings
from db.models import SessionContext, AgentResult, HandoffPayload
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
from knowledge.service import get_knowledge
from tools.campaign_tools import (
    TOOLS as CAMPAIGN_TOOLS,
    CAMPAIGN_TOOL_NAMES,
    execute_campaign_tool,
)

logger = logging.getLogger(__name__)

ALL_TOOLS = CAMPAIGN_TOOLS

_COMMERCIAL_HANDOFF_PHRASES = [
    "vou te encaminhar", "vou transferir", "nosso setor comercial",
    "colega do comercial", "equipe comercial", "agente comercial",
]
_SCHEDULING_HANDOFF_PHRASES = [
    "agente de agendamento", "vou te encaminhar para agendamento",
    "equipe de agendamento",
]


def _exam_policy_facts() -> list[str]:
    """Snapshot da política de exames para L5."""
    knowledge = get_knowledge()
    exam_info = knowledge.get("clinic_info", "exam_policy") or {}
    return [
        f"política de exames: jejum={exam_info.get('lab_fasting_hours', '8 a 12 horas')} | "
        f"prazo de resultado={exam_info.get('result_turnaround', '5 dias úteis')} | "
        f"pedido médico={'obrigatório' if exam_info.get('medical_order_required') else 'não obrigatório'}"
    ]


def _exam_content_fact(ctx: SessionContext) -> list[str]:
    """Se paciente enviou um PDF/texto de exame, inclui no L5."""
    if ctx.exam_content and not ctx.exam_content.startswith("http"):
        # limita o tamanho — o corpo pode ser grande, mas L5 é metadata, não doc
        snippet = ctx.exam_content[:2000]
        return [f"conteúdo do exame enviado pelo paciente (extraído):\n{snippet}"]
    return []


class ExamsAgent(BaseAgent):
    agent_type = "exams"
    model = "claude-haiku-4-5"

    async def run(self, ctx: SessionContext) -> AgentResult:
        settings = get_settings()
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        patient_name = (ctx.patient_metadata or {}).get("name", "Desconhecido")
        logger.info(
            "[EXAMS] Iniciando | patient=%s (%s) | exam_content=%s",
            patient_name, ctx.patient_phone, bool(ctx.exam_content),
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

        extra_facts = _exam_policy_facts() + _exam_content_fact(ctx)
        session_metadata = format_session_state(ctx, extra_facts=extra_facts)

        system, trace = compose_agent_system(
            safety=load_prompt("_safety"),
            core_identity=load_prompt("exams"),
            business_rules=load_prompt("_business_rules"),
            campaigns_index=format_campaigns_index(service),
            campaign_block=campaign_block,
            session_metadata=session_metadata,
        )
        logger.info(
            "[EXAMS] Trace | patient=%s | layers=%s | campaign_id=%s",
            patient_name, trace["layers_present"], campaign_id,
        )

        messages = self._build_history(ctx)
        if ctx.exam_content and ctx.exam_content.startswith("http"):
            messages = self._inject_image_into_last_message(messages, ctx.exam_content)

        reply = None
        for _ in range(5):
            response = await client.messages.create(
                model=self.model,
                max_tokens=384,
                temperature=0.3,
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

        reply, conflicts = extract_and_strip_conflicts(reply)
        if conflicts:
            logger.warning(
                "[EXAMS] Conflict | patient=%s | conflicts=%s",
                patient_name, conflicts,
            )

        handoff_target = None
        handoff_payload = None
        patient_name_out = (ctx.patient_metadata or {}).get("name")

        if reply:
            reply_lower = reply.lower()
            if any(p in reply_lower for p in _COMMERCIAL_HANDOFF_PHRASES):
                handoff_target = "commercial"
                handoff_payload = HandoffPayload(
                    type="to_commercial",
                    patient_name=patient_name_out,
                    reason="Encaminhado pelo agente de exames",
                )
                logger.info("[EXAMS] Handoff → commercial | patient=%s", patient_name_out)
            elif any(p in reply_lower for p in _SCHEDULING_HANDOFF_PHRASES):
                handoff_target = "scheduling"
                handoff_payload = HandoffPayload(
                    type="to_scheduling",
                    patient_name=patient_name_out,
                    reason="Paciente quer agendar consulta após análise de exame",
                )
                logger.info("[EXAMS] Handoff → scheduling | patient=%s", patient_name_out)

        logger.info(
            "[EXAMS] Resposta | patient=%s | handoff=%s",
            patient_name_out, handoff_target or "Nenhum",
        )

        return AgentResult(
            reply=reply or None,
            handoff_target=handoff_target,
            handoff_payload=handoff_payload,
        )

    def _inject_image_into_last_message(
        self, messages: list[dict], image_url: str
    ) -> list[dict]:
        """Substitui placeholder [IMAGE] pelo content block de visão."""
        if not messages:
            return messages

        last = messages[-1]
        if last["role"] != "user":
            return messages

        content = last["content"]
        if isinstance(content, str) and "[IMAGE]" in content:
            text_part = content.replace("[IMAGE]", "").strip() or "Analise este exame."
            messages[-1] = {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "url", "url": image_url},
                    },
                    {"type": "text", "text": text_part},
                ],
            }
        return messages
