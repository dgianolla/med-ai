import logging
from anthropic import AsyncAnthropic

from config import get_settings
from db.models import SessionContext, AgentResult, HandoffPayload
from agents.base_agent import BaseAgent
from agents.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

# Frases que indicam que Claude está encaminhando para outro agente
_COMMERCIAL_HANDOFF_PHRASES = [
    "vou te encaminhar", "vou transferir", "nosso setor comercial",
    "colega do comercial", "equipe comercial", "agente comercial",
]
_SCHEDULING_HANDOFF_PHRASES = [
    "agente de agendamento", "vou te encaminhar para agendamento",
    "equipe de agendamento",
]


class ExamsAgent(BaseAgent):
    agent_type = "exams"
    model = "claude-sonnet-4-6"

    async def run(self, ctx: SessionContext) -> AgentResult:
        settings = get_settings()
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        system = load_prompt("exams")

        # Contexto do handoff
        if ctx.handoff_payload and ctx.handoff_payload.patient_name:
            system += f"\n\nO paciente já se identificou como: {ctx.handoff_payload.patient_name}"

        # Conteúdo de exame já processado (PDF extraído ou transcrição)
        if ctx.exam_content and not ctx.exam_content.startswith("http"):
            system += f"\n\n## CONTEÚDO DO EXAME ENVIADO PELO PACIENTE\n{ctx.exam_content}"

        messages = self._build_history(ctx)

        # Imagem enviada via URL pública — injeta como bloco de visão
        if ctx.exam_content and ctx.exam_content.startswith("http"):
            messages = self._inject_image_into_last_message(messages, ctx.exam_content)

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

        # Detecta handoff explícito na resposta do Claude
        handoff_target = None
        handoff_payload = None
        patient_name = (ctx.patient_metadata or {}).get("name")

        if reply:
            reply_lower = reply.lower()
            if any(p in reply_lower for p in _COMMERCIAL_HANDOFF_PHRASES):
                handoff_target = "commercial"
                handoff_payload = HandoffPayload(
                    type="to_commercial",
                    patient_name=patient_name,
                    reason="Encaminhado pelo agente de exames",
                )
            elif any(p in reply_lower for p in _SCHEDULING_HANDOFF_PHRASES):
                handoff_target = "scheduling"
                handoff_payload = HandoffPayload(
                    type="to_scheduling",
                    patient_name=patient_name,
                    reason="Paciente quer agendar consulta após análise de exame",
                )

        return AgentResult(
            reply=reply,
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
