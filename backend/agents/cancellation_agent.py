import json
import logging
from datetime import datetime
from anthropic import AsyncAnthropic

from config import get_settings
from db.models import SessionContext, AgentResult
from agents.base_agent import BaseAgent
from agents.prompt_loader import load_prompt
from tools.cancellation_tools import TOOLS
from knowledge.tools import TOOLS as KNOWLEDGE_TOOLS
from integrations.scheduling_api import cancel_appointment

logger = logging.getLogger(__name__)

ALL_TOOLS = TOOLS + KNOWLEDGE_TOOLS


class CancellationAgent(BaseAgent):
    agent_type = "cancellation"
    model = "claude-sonnet-4-6"

    async def run(self, ctx: SessionContext) -> AgentResult:
        settings = get_settings()
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        patient_name = (ctx.patient_metadata or {}).get("name", "Desconhecido")
        logger.info("[CANCELLATION] Iniciando | patient=%s (%s)", patient_name, ctx.patient_phone)

        now = datetime.now()
        system = load_prompt("cancellation").format(
            today=now.strftime("%Y-%m-%d"),
            month=now.strftime("%m"),
            year=now.strftime("%Y"),
        )

        # Injeta contexto acumulado
        if ctx.handoff_payload and ctx.handoff_payload.patient_name:
            system += f"\n\nO paciente já se identificou como: {ctx.handoff_payload.patient_name}"

        if ctx.handoff_payload and ctx.handoff_payload.context:
            context = ctx.handoff_payload.context
            collected_info = []
            if context.get("scheduled_date"):
                collected_info.append(f"Agendamento em: {context['scheduled_date']}")
            if context.get("scheduled_time"):
                collected_info.append(f"Horário: {context['scheduled_time']}")
            if context.get("specialty"):
                collected_info.append(f"Especialidade: {context['specialty']}")
            if context.get("appointment_id"):
                collected_info.append(f"ID do agendamento: {context['appointment_id']}")
            if collected_info:
                system += "\n\n## DADOS DO AGENDAMENTO\n" + "\n".join(collected_info)

        messages = self._build_history(ctx)

        # Loop agentico
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

                    # Salva dados se cancelou com sucesso
                    if block.name == "cancel_appointment" and result.get("success"):
                        ctx.patient_metadata = ctx.patient_metadata or {}
                        ctx.patient_metadata["cancelled"] = True
                        ctx.patient_metadata["cancelled_at"] = datetime.now().isoformat()
                        ctx.patient_metadata["cancel_reason"] = block.input.get("reason", "Não informado")

                messages.append({"role": "user", "content": tool_results})
                continue

            # Extrai resposta de texto
            reply = next(
                (b.text for b in response.content if hasattr(b, "text")),
                None,
            )

            # Verifica se o cancelamento foi concluído
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
                reply=reply,
                session_updates=ctx.patient_metadata,
                done=done,
            )

        return AgentResult(
            reply="Desculpe, tive um problema ao processar sua solicitação. Por favor, tente novamente.",
        )

    async def _execute_tool(self, tool_name: str, tool_input: dict) -> dict:
        try:
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
