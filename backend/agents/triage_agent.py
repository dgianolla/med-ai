import json
import logging
from anthropic import AsyncAnthropic

from config import get_settings
from db.models import SessionContext, AgentResult, HandoffPayload
from agents.base_agent import BaseAgent
from agents.prompt_loader import load_prompt

logger = logging.getLogger(__name__)



class TriageAgent(BaseAgent):
    agent_type = "triage"
    model = "claude-haiku-4-5"

    async def run(self, ctx: SessionContext) -> AgentResult:
        settings = get_settings()
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        patient_name = (ctx.patient_metadata or {}).get("name", "Desconhecido")
        logger.info("[TRIAGE] Iniciando | patient=%s (%s)", patient_name, ctx.patient_phone)

        # Última mensagem do paciente
        last_user_msg = next(
            (m["content"] for m in reversed(ctx.conversation_history) if m["role"] == "user"),
            "",
        )

        # Contexto adicional se for mídia
        content = last_user_msg
        if ctx.exam_content:
            content = f"[Paciente enviou exame]\n{ctx.exam_content}"

        try:
            response = await client.messages.create(
                model=self.model,
                max_tokens=100,
                system=load_prompt("triage"),
                messages=[{"role": "user", "content": content}],
            )

            raw = response.content[0].text.strip()
            # Remove markdown code block se presente
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            data = json.loads(raw)
            target = data.get("target", "scheduling")
            reason = data.get("reason", "")

            logger.info(
                "[TRIAGE] Decisão | patient=%s | target=%s | reason=%s",
                patient_name, target, reason,
            )

            return AgentResult(
                reply=None,  # Triagem nunca responde ao paciente
                handoff_target=target,
                handoff_payload=HandoffPayload(
                    type=f"to_{target}",
                    patient_name=ctx.patient_metadata.get("name") if ctx.patient_metadata else None,
                    reason=reason,
                    exam_content=ctx.exam_content,
                ),
            )

        except json.JSONDecodeError:
            logger.warning("TriageAgent retornou JSON inválido — defaulting to scheduling")
            return AgentResult(
                handoff_target="scheduling",
                handoff_payload=HandoffPayload(type="to_scheduling"),
            )
        except Exception as e:
            logger.error("Erro no TriageAgent: %s", e)
            return AgentResult(
                handoff_target="scheduling",
                handoff_payload=HandoffPayload(type="to_scheduling"),
            )
