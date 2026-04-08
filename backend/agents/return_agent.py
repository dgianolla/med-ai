import json
import logging
from datetime import datetime
from anthropic import AsyncAnthropic

from config import get_settings
from db.models import SessionContext, AgentResult
from agents.base_agent import BaseAgent
from agents.prompt_loader import load_prompt
from tools.return_tools import TOOLS
from knowledge.tools import TOOLS as KNOWLEDGE_TOOLS, get_clinic_info
from integrations.scheduling_api import (
    get_available_dates,
    get_available_times,
    create_appointment,
    get_professionals_for_specialty,
    CONVENIOS,
)

logger = logging.getLogger(__name__)

ALL_TOOLS = TOOLS + KNOWLEDGE_TOOLS


class ReturnAgent(BaseAgent):
    agent_type = "return"
    model = "claude-sonnet-4-6"

    async def run(self, ctx: SessionContext) -> AgentResult:
        settings = get_settings()
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        patient_name = (ctx.patient_metadata or {}).get("name", "Desconhecido")
        logger.info("[RETURN] Iniciando | patient=%s (%s)", patient_name, ctx.patient_phone)

        now = datetime.now()
        system = load_prompt("return").format(
            today=now.strftime("%Y-%m-%d"),
            month=now.strftime("%m"),
            year=now.strftime("%Y"),
        )

        if ctx.handoff_payload and ctx.handoff_payload.patient_name:
            system += f"\n\nO paciente já se identificou como: {ctx.handoff_payload.patient_name}"
        if ctx.handoff_payload and ctx.handoff_payload.last_consult_date:
            system += f"\nData da última consulta registrada: {ctx.handoff_payload.last_consult_date}"

        messages = self._build_history(ctx)

        for _ in range(10):
            response = await client.messages.create(
                model=self.model,
                max_tokens=1024,
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

                    if block.name == "schedule_return" and result.get("success"):
                        ctx.patient_metadata = ctx.patient_metadata or {}
                        ctx.patient_metadata.update({
                            "name": block.input.get("patient_name"),
                            "phone": block.input.get("patient_phone"),
                            "specialty": block.input.get("specialty"),
                            "return_date": block.input.get("date"),
                            "return_time": block.input.get("hora_inicio"),
                        })

                messages.append({"role": "user", "content": tool_results})
                continue

            reply = next(
                (b.text for b in response.content if hasattr(b, "text")),
                None,
            )

            done = reply is not None and any(word in reply.lower() for word in [
                "retorno confirmado", "retorno agendado", "consulta de retorno marcada",
                "agendamento confirmado", "confirmado com sucesso",
            ])

            logger.info(
                "[RETURN] Resposta gerada | patient=%s | reply=%s | done=%s",
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
            if tool_name == "get_clinic_info":
                return await get_clinic_info(tool_input["query"])

            if tool_name == "get_available_dates":
                specialty = tool_input["specialty"]
                month = tool_input["month"]
                year = tool_input["year"]

                professionals = get_professionals_for_specialty(specialty)
                if not professionals:
                    return {"error": f"Especialidade '{specialty}' não disponível."}

                all_dates = []
                for prof in professionals:
                    dates = await get_available_dates(prof["id"], month, year)
                    for d in dates:
                        all_dates.append({
                            "data": d,
                            "profissional_id": prof["id"],
                            "profissional_nome": prof["nome"],
                        })

                if not all_dates:
                    return {"datas": [], "mensagem": f"Não há datas disponíveis em {month}/{year}."}
                return {"datas": all_dates}

            elif tool_name == "get_available_times":
                specialty = tool_input["specialty"]
                date = tool_input["date"]

                professionals = get_professionals_for_specialty(specialty)
                if not professionals:
                    return {"error": f"Especialidade '{specialty}' não disponível."}

                all_times = []
                for prof in professionals:
                    times = await get_available_times(prof["id"], date)
                    for t in times:
                        all_times.append({
                            "horaInicio": t["horaInicio"],
                            "horaFim": t["horaFim"],
                            "profissional_id": prof["id"],
                            "profissional_nome": prof["nome"],
                        })

                if not all_times:
                    return {"horarios": [], "mensagem": f"Não há horários disponíveis em {date}."}
                return {"horarios": all_times}

            elif tool_name == "schedule_return":
                specialty = tool_input["specialty"]
                professionals = get_professionals_for_specialty(specialty)
                if not professionals:
                    return {"error": f"Especialidade '{specialty}' não disponível."}

                prof = professionals[0]
                result = await create_appointment(
                    professional_id=prof["id"],
                    esp_id=prof["esp_id"],
                    date=tool_input["date"],
                    hora_inicio=tool_input["hora_inicio"],
                    hora_fim=tool_input["hora_fim"],
                    patient_name=tool_input["patient_name"],
                    patient_phone=tool_input["patient_phone"],
                    convenio_id=48339,  # retorno sempre particular (gratuito pela clínica)
                )
                return {"success": True, "agendamento": result}

        except Exception as e:
            logger.error("Erro na tool %s: %s", tool_name, e)
            return {"error": str(e)}
