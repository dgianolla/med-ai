import logging
from anthropic import AsyncAnthropic

from config import get_settings
from db.models import SessionContext, AgentResult, HandoffPayload
from agents.base_agent import BaseAgent
from agents.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

_SCHEDULING_HANDOFF_PHRASES = [
    "vou te encaminhar para agendamento", "agente de agendamento",
    "equipe de agendamento", "vou te encaminhar para a agenda",
]

_DONE_PHRASES = [
    "até logo", "até mais", "obrigado por entrar em contato",
    "qualquer dúvida", "boa consulta", "tenha um ótimo dia",
]


class CommercialAgent(BaseAgent):
    agent_type = "commercial"
    model = "claude-sonnet-4-6"

    async def run(self, ctx: SessionContext) -> AgentResult:
        settings = get_settings()
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        system = load_prompt("commercial")

        # Contexto do handoff (ex: veio de Exames com exames específicos)
        if ctx.handoff_payload:
            payload = ctx.handoff_payload
            if payload.patient_name:
                system += f"\n\nO paciente já se identificou como: {payload.patient_name}"
            if payload.reason:
                system += f"\nMotivo do encaminhamento: {payload.reason}"
            if payload.exam_ids:
                system += f"\nExames de interesse: {', '.join(payload.exam_ids)}"

        messages = self._build_history(ctx)

        response = await client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system,
            messages=messages,
        )

        reply = next(
            (b.text for b in response.content if hasattr(b, "text")),
            None,
        )

        handoff_target = None
        handoff_payload = None
        patient_name = (ctx.patient_metadata or {}).get("name")
        done = False

        if reply:
            reply_lower = reply.lower()

            if any(p in reply_lower for p in _SCHEDULING_HANDOFF_PHRASES):
                handoff_target = "scheduling"
                handoff_payload = HandoffPayload(
                    type="to_scheduling",
                    patient_name=patient_name,
                    reason="Paciente quer agendar consulta após atendimento comercial",
                )
            elif any(p in reply_lower for p in _DONE_PHRASES):
                done = True

        return AgentResult(
            reply=reply,
            handoff_target=handoff_target,
            handoff_payload=handoff_payload,
            done=done,
        )
