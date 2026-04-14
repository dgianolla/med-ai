import json
import logging

from anthropic import AsyncAnthropic

from agents.base_agent import BaseAgent
from agents.prompt_loader import load_prompt
from campaigns.service import get_campaign_service
from config import get_settings
from db.models import AgentResult, HandoffPayload, SessionContext
from knowledge.tools import TOOLS as KNOWLEDGE_TOOLS, get_clinic_info

logger = logging.getLogger(__name__)

ALL_TOOLS = KNOWLEDGE_TOOLS

_SCHEDULING_HANDOFF_PHRASES = [
    "vou te encaminhar para agendamento",
    "vou te encaminhar pro agendamento",
    "vou te passar para agendamento",
    "vou te passar pro agendamento",
]

_DONE_PHRASES = [
    "até logo",
    "até mais",
    "obrigado por entrar em contato",
    "qualquer dúvida",
    "fico à disposição",
]


class CampaignAgent(BaseAgent):
    agent_type = "campaign"
    model = "claude-sonnet-4-6"

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
                reply="Posso te ajudar por aqui. Me conta se esse atendimento é para você ou para outra pessoa?",
            )

        logger.info(
            "[CAMPAIGN] Context | patient=%s | campaign=%s | specialty=%s | history=%s",
            patient_name,
            campaign.nome,
            campaign.especialidade or "-",
            len(ctx.conversation_history),
        )

        system = load_prompt("campaign")
        system += (
            "\n\n## CAMPANHA ATIVA\n"
            f"{campaign.raw.strip()}\n\n"
            "Regra explícita: siga o fluxo de atendimento na ordem; use get_clinic_info "
            "para dados canônicos da clínica; não invente nada fora deste .md e da knowledge base."
        )

        if ctx.handoff_payload:
            payload = ctx.handoff_payload
            if payload.patient_name:
                system += f"\n\nPaciente: {payload.patient_name}"
            if payload.reason:
                system += f"\nMotivo do encaminhamento: {payload.reason}"

        if ctx.patient_metadata:
            collected = []
            for key in ("name", "convenio", "specialty", "interest"):
                if ctx.patient_metadata.get(key):
                    collected.append(f"{key}: {ctx.patient_metadata[key]}")
            if collected:
                system += "\n\n## METADATA DA SESSÃO\n" + "\n".join(collected)

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

                    if block.name == "get_clinic_info":
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

        handoff_target = None
        handoff_payload = None
        done = False

        if reply:
            reply_lower = reply.lower()

            if any(phrase in reply_lower for phrase in _SCHEDULING_HANDOFF_PHRASES):
                handoff_context = {
                    "campaign_name": campaign.nome,
                    "lead_source": "campaign",
                    "invisible_handoff": True,
                    **(
                        ctx.handoff_payload.context
                        if ctx.handoff_payload and ctx.handoff_payload.context
                        else {}
                    ),
                }
                if campaign.especialidade:
                    handoff_context["specialty"] = campaign.especialidade

                handoff_payload = HandoffPayload(
                    type="to_scheduling",
                    patient_name=(ctx.patient_metadata or {}).get("name"),
                    reason=f"Paciente avançou na campanha {campaign.nome} e quer agendar",
                    specialty_needed=campaign.especialidade,
                    context=handoff_context,
                )
                handoff_target = "scheduling"
                # O handoff para agendamento é interno: o paciente deve receber
                # a próxima mensagem já do fluxo de agenda, sem "te encaminhar".
                reply = None
                logger.info(
                    "[CAMPAIGN] Handoff | kind=invisivel | from=campaign | to=scheduling | patient=%s | campaign=%s | specialty=%s",
                    patient_name, campaign.nome, campaign.especialidade,
                )
            elif any(phrase in reply_lower for phrase in _DONE_PHRASES):
                done = True
                logger.info("[CAMPAIGN] Sessão encerrada | patient=%s | campaign=%s", patient_name, campaign.nome)

        logger.info(
            "[CAMPAIGN] Result | patient=%s | campaign=%s | handoff=%s | done=%s | replied=%s",
            patient_name, campaign.nome, handoff_target or "Nenhum", done, bool(reply),
        )

        return AgentResult(
            reply=reply,
            handoff_target=handoff_target,
            handoff_payload=handoff_payload,
            done=done,
        )
