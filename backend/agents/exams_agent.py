import logging
from anthropic import AsyncAnthropic

from config import get_settings
from db.models import SessionContext, AgentResult, HandoffPayload
from agents.base_agent import BaseAgent
from agents.prompt_loader import load_prompt
from knowledge.service import get_knowledge

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

        patient_name = (ctx.patient_metadata or {}).get("name", "Desconhecido")
        logger.info("[EXAMS] Iniciando | patient=%s (%s) | exam_content=%s", patient_name, ctx.patient_phone, bool(ctx.exam_content))

        system = load_prompt("exams")

        # Injeta informações da clínica dinamicamente
        knowledge = get_knowledge()
        exam_info = knowledge.get("clinic_info", "exam_policy")
        system += f"\n\n## POLÍTICA DE EXAMES DA CLÍNICA\n"
        system += f"- Jejum: {exam_info.get('lab_fasting_hours', '8 a 12 horas')}\n"
        system += f"- Prazo de resultado: {exam_info.get('result_turnaround', '5 dias úteis')}\n"
        system += f"- Pedido médico: {'obrigatório' if exam_info.get('medical_order_required') else 'não obrigatório'}"

        # Contexto do handoff
        if ctx.handoff_payload and ctx.handoff_payload.patient_name:
            system += f"\n\nO paciente já se identificou como: {ctx.handoff_payload.patient_name}"

        # Verifica se veio de handoff automático do comercial (checkup)
        if ctx.handoff_payload and ctx.handoff_payload.context:
            context = ctx.handoff_payload.context
            if context.get("auto_handoff_from_commercial") and context.get("checkup_packages_sent"):
                system += (
                    "\n\n## CONTEXTO ESPECIAL: PACIENTE RECEBEU INFO DE CHECKUP\n"
                    "O paciente acabou de receber informações sobre pacotes de checkup. "
                    "Pergunte se ele tem interesse em algum combo específico e se deseja prosseguir "
                    "com o agendamento. Seja proativo: ofereça ajudar a escolher o combo mais adequado. "
                    "Use emojis verdes (💚, 🌿) para manter a identidade da marca."
                )

        # Conteúdo de exame já processado (PDF extraído ou transcrição)
        if ctx.exam_content and not ctx.exam_content.startswith("http"):
            system += f"\n\n## CONTEÚDO DO EXAME ENVIADO PELO PACIENTE\n{ctx.exam_content}"

        messages = self._build_history(ctx)

        # Imagem enviada via URL pública — injeta como bloco de visão
        if ctx.exam_content and ctx.exam_content.startswith("http"):
            messages = self._inject_image_into_last_message(messages, ctx.exam_content)

        response = await client.messages.create(
            model=self.model,
            max_tokens=384,
            temperature=0.3,
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
                logger.info("[EXAMS] Handoff → commercial | patient=%s", patient_name)
            elif any(p in reply_lower for p in _SCHEDULING_HANDOFF_PHRASES):
                handoff_target = "scheduling"
                handoff_payload = HandoffPayload(
                    type="to_scheduling",
                    patient_name=patient_name,
                    reason="Paciente quer agendar consulta após análise de exame",
                )
                logger.info("[EXAMS] Handoff → scheduling | patient=%s", patient_name)

        logger.info("[EXAMS] Resposta | patient=%s | handoff=%s", patient_name, handoff_target or "Nenhum")

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
