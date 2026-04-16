import json
import logging
from datetime import datetime
from anthropic import AsyncAnthropic
from anthropic import APIStatusError

from config import get_settings
from db.models import SessionContext, AgentResult
from agents.base_agent import BaseAgent
from agents.prompt_loader import load_prompt
from tools.scheduling_tools import TOOLS
from knowledge.tools import TOOLS as KNOWLEDGE_TOOLS, get_clinic_info
from knowledge.service import get_knowledge
from integrations.scheduling_api import (
    get_available_dates,
    get_available_times,
    get_agenda,
    create_appointment,
    get_professionals_for_specialty,
    CONVENIOS,
)
from services.priority_leads import create_priority_lead

logger = logging.getLogger(__name__)

# Combina scheduling tools + knowledge tools
ALL_TOOLS = TOOLS + KNOWLEDGE_TOOLS


def _short(text: str | None, limit: int = 120) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


class SchedulingAgent(BaseAgent):
    agent_type = "scheduling"
    model = "claude-haiku-4-5"

    async def run(self, ctx: SessionContext) -> AgentResult:
        settings = get_settings()
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        patient_name = (ctx.patient_metadata or {}).get("name", "Desconhecido")
        logger.info("[SCHEDULING] Iniciando | patient=%s (%s)", patient_name, ctx.patient_phone)

        messages = self._build_history(ctx)
        logger.info(
            "[SCHEDULING] Context | patient=%s | history=%s | handoff_type=%s | specialty=%s | context_keys=%s",
            patient_name,
            len(messages),
            ctx.handoff_payload.type if ctx.handoff_payload else None,
            ctx.handoff_payload.specialty_needed if ctx.handoff_payload else None,
            sorted((ctx.handoff_payload.context or {}).keys()) if ctx.handoff_payload and ctx.handoff_payload.context else [],
        )

        # Injeta data atual no prompt (substitui {today}, {month}, {year})
        now = datetime.now()
        system = load_prompt("scheduling").format(
            today=now.strftime("%Y-%m-%d"),
            month=now.strftime("%m"),
            year=now.strftime("%Y"),
        )

        # Injeta informações dinâmicas da clínica
        knowledge = get_knowledge()
        payment_info = knowledge.get("clinic_info", "payment")
        if payment_info:
            system += (
                f"\n\n## FORMAS DE PAGAMENTO (dados dinâmicos)\n"
                f"Métodos: {', '.join(payment_info.get('methods', []))}\n"
                f"Chave PIX: {payment_info.get('pix_key', 'N/A')}\n"
                f"Parcelamento: Consultas até {payment_info.get('installments', {}).get('consultas', '2x')} | "
                f"Exames/Combos até {payment_info.get('installments', {}).get('exames_combos', '10x')}"
            )

        arrival_info = knowledge.get("clinic_info", "arrival_policy")
        if arrival_info:
            system += (
                f"\n\n## POLÍTICA DE CHEGADA\n"
                f"Chegar {arrival_info.get('arrive_minutes_before', 15)} minutos antes | "
                f"Tolerância: {arrival_info.get('tolerance_minutes', 15)} minutos"
            )

        # Injeta contexto do handoff se vier da Triagem
        if ctx.handoff_payload and ctx.handoff_payload.patient_name:
            system += f"\n\nO paciente já se identificou como: {ctx.handoff_payload.patient_name}"
        if ctx.handoff_payload and ctx.handoff_payload.specialty_needed:
            system += (
                f"\nA especialidade deste atendimento já foi definida anteriormente: "
                f"{ctx.handoff_payload.specialty_needed}. Priorize essa especialidade e "
                f"não volte a perguntar qual especialidade o paciente quer."
            )

        # Combo em curso → esta é a etapa de CONSULTA do combo
        if ctx.handoff_payload and ctx.handoff_payload.combo_id:
            combo_ctx = ctx.handoff_payload.context or {}
            combo_name = combo_ctx.get("combo_name", ctx.handoff_payload.combo_id)
            system += (
                f"\n\n## CONTEXTO DE COMBO\n"
                f"O paciente fechou o combo: **{combo_name}** (id: {ctx.handoff_payload.combo_id}).\n"
                f"Sua tarefa aqui é agendar apenas a ETAPA DE CONSULTA desse combo — "
                f"não é uma consulta avulsa. A especialidade da consulta já veio resolvida "
                f"pelo combo e NÃO deve ser perguntada novamente ao paciente."
            )
            if combo_ctx.get("collection_schedule_required"):
                system += (
                    f"\nEste combo também tem etapa de COLETA DE EXAMES que será agendada "
                    f"em um momento separado. Não tente marcar a coleta aqui — apenas a consulta. "
                    f"Se o paciente perguntar sobre a coleta, diga que depois de fechar o horário "
                    f"da consulta a gente combina a coleta."
                )
            # Particular é o default para combos (são produtos fechados)
            if not combo_ctx.get("convenio"):
                system += (
                    f"\nCombos são sempre atendimento particular. "
                    f"Não pergunte convênio para este atendimento."
                )

        # Injeta contexto acumulado de handoffs anteriores
        if ctx.handoff_payload and ctx.handoff_payload.context:
            context = ctx.handoff_payload.context
            # Dados coletados por agentes anteriores
            collected_info = []
            if context.get("convenio"):
                collected_info.append(f"Convênio: {context['convenio']}")
            if context.get("specialty"):
                collected_info.append(f"Especialidade já mencionada: {context['specialty']}")
            if context.get("scheduled_date"):
                collected_info.append(f"Já possui agendamento em {context['scheduled_date']} às {context.get('scheduled_time', '')}")
            if context.get("appointment_id"):
                collected_info.append(f"ID do agendamento: {context['appointment_id']}")
            if collected_info:
                system += "\n\n## INFORMAÇÕES COLETADAS EM INTERAÇÕES ANTERIORES\n" + "\n".join(collected_info)

        # Nota sobre consulta de preços
        system += (
            "\n\n## NOTA: Se o paciente perguntar sobre PREÇOS, VALORES ou CUSTOS de consultas, "
            "exames ou combos, NÃO invente valores. Use a tool `get_clinic_info` para consultar "
            "os preços atualizados. Ex: get_clinic_info(query='qual o valor da consulta de cardiologia')."
        )

        # Loop agentico: Claude pode chamar múltiplas tools antes de responder ao paciente
        for _ in range(10):  # max 10 iterações por mensagem
            try:
                response = await client.messages.create(
                    model=self.model,
                    max_tokens=384,
                    temperature=0.7,
                    system=system,
                    tools=ALL_TOOLS,
                    messages=messages,
                )
            except APIStatusError as e:
                logger.error(
                    "[SCHEDULING] Provider error | status=%s | patient=%s | handoff_type=%s | specialty=%s | messages=%s | detail=%s",
                    getattr(e, "status_code", "N/A"),
                    patient_name,
                    ctx.handoff_payload.type if ctx.handoff_payload else None,
                    ctx.handoff_payload.specialty_needed if ctx.handoff_payload else None,
                    len(messages),
                    getattr(e, "body", None),
                )
                return AgentResult(
                    reply="Desculpe, tive um problema interno ao continuar seu agendamento. Pode me dizer novamente qual especialidade ou exame você quer agendar?",
                )
            except Exception as e:
                logger.exception(
                    "[SCHEDULING] Unexpected provider failure | patient=%s | messages=%s",
                    patient_name,
                    len(messages),
                )
                return AgentResult(
                    reply="Desculpe, tive um problema interno ao continuar seu agendamento. Pode me dizer novamente qual especialidade ou exame você quer agendar?",
                )

            # Claude quer usar uma tool
            if response.stop_reason == "tool_use":
                tool_names = [block.name for block in response.content if getattr(block, "type", None) == "tool_use"]
                logger.info(
                    "[SCHEDULING] Tool request | patient=%s | tools=%s",
                    patient_name,
                    tool_names,
                )
                # Adiciona resposta do Claude (com tool_use blocks) ao histórico
                messages.append({"role": "assistant", "content": response.content})

                # Executa cada tool solicitada
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    logger.info(
                        "[SCHEDULING] Tool call | patient=%s | tool=%s | input=%s",
                        patient_name,
                        block.name,
                        _short(json.dumps(block.input, ensure_ascii=False), 200),
                    )
                    result = await self._execute_tool(block.name, block.input, ctx)
                    logger.info(
                        "[SCHEDULING] Tool result | patient=%s | tool=%s | output=%s",
                        patient_name,
                        block.name,
                        _short(json.dumps(result, ensure_ascii=False), 240),
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })

                    # Salva dados coletados no contexto da sessão
                    if block.name == "schedule_appointment" and result.get("success"):
                        ctx.patient_metadata = ctx.patient_metadata or {}
                        ctx.patient_metadata.update({
                            "name": block.input.get("patient_name"),
                            "phone": block.input.get("patient_phone"),
                            "convenio": block.input.get("convenio", "particular"),
                            "specialty": block.input.get("specialty"),
                            "scheduled_date": block.input.get("date"),
                            "scheduled_time": block.input.get("hora_inicio"),
                        })
                        # Salva appointment_id se retornado pela API
                        appointment_data = result.get("agendamento", {})
                        if appointment_data.get("id"):
                            ctx.patient_metadata["appointment_id"] = appointment_data["id"]

                messages.append({"role": "user", "content": tool_results})
                continue

            # Claude terminou — extrai resposta de texto
            reply = next(
                (b.text for b in response.content if hasattr(b, "text")),
                None,
            )

            # Verifica se o agendamento foi concluído
            done = (
                reply is not None and
                any(word in reply.lower() for word in [
                    "agendamento confirmado", "consulta agendada", "confirmado com sucesso",
                    "sua consulta foi marcada", "agendamento realizado",
                ])
            )

            logger.info(
                "[SCHEDULING] Reply | patient=%s | done=%s | text=%s",
                patient_name, done, _short(reply),
            )

            return AgentResult(
                reply=reply,
                session_updates=ctx.patient_metadata,
                done=done,
            )

        return AgentResult(
            reply="Desculpe, tive um problema ao processar sua solicitação. Por favor, tente novamente.",
        )

    async def _execute_tool(self, tool_name: str, tool_input: dict, ctx: SessionContext) -> dict:
        """Executa a tool solicitada pelo Claude e retorna o resultado."""
        try:
            if tool_name == "get_clinic_info":
                return await get_clinic_info(tool_input["query"])

            if tool_name == "get_agenda":
                agenda = await get_agenda(tool_input["date_start"], tool_input["date_end"])
                professional_id = tool_input["professional_id"]
                # Filtra apenas agendamentos do profissional solicitado
                prof_agenda = [a for a in agenda if a.get("profissionalSaude", {}).get("id") == professional_id]
                # Conta convênios (convenio presente e não particular)
                convenio_count = sum(
                    1 for a in prof_agenda
                    if a.get("convenio") and a["convenio"].get("id") != 48339
                )
                return {
                    "total_agendamentos": len(prof_agenda),
                    "total_convenios": convenio_count,
                    "agendamentos": prof_agenda,
                }

            elif tool_name == "get_available_dates":
                specialty = tool_input["specialty"]
                month = tool_input["month"]
                year = tool_input["year"]

                professionals = get_professionals_for_specialty(specialty)
                if not professionals:
                    return {"error": f"Especialidade '{specialty}' não disponível no momento."}

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
                    return {"datas": [], "mensagem": f"Não há datas disponíveis em {month}/{year} para {specialty}."}

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

            elif tool_name == "schedule_appointment":
                specialty = tool_input["specialty"]
                professionals = get_professionals_for_specialty(specialty)
                if not professionals:
                    return {"error": f"Especialidade '{specialty}' não disponível."}

                prof = professionals[0]
                convenio_key = tool_input.get("convenio", "particular").lower()
                convenio_id = CONVENIOS.get(convenio_key, 48339) or 48339

                result = await create_appointment(
                    professional_id=prof["id"],
                    esp_id=prof["esp_id"],
                    date=tool_input["date"],
                    hora_inicio=tool_input["hora_inicio"],
                    hora_fim=tool_input["hora_fim"],
                    patient_name=tool_input["patient_name"],
                    patient_phone=tool_input["patient_phone"],
                    convenio_id=convenio_id,
                )

                await self._maybe_create_priority_card(
                    ctx=ctx,
                    tool_input=tool_input,
                    professional=prof,
                    appointment=result,
                )
                return {"success": True, "agendamento": result}

        except Exception as e:
            logger.error("Erro na tool %s: %s", tool_name, e)
            return {"error": str(e)}

    async def _maybe_create_priority_card(
        self,
        *,
        ctx: SessionContext,
        tool_input: dict,
        professional: dict,
        appointment: dict,
    ) -> None:
        convenio = (tool_input.get("convenio") or "particular").lower()
        context = ctx.handoff_payload.context if ctx.handoff_payload and ctx.handoff_payload.context else {}
        lead_source = context.get("lead_source") or (ctx.handoff_payload.type.replace("to_", "") if ctx.handoff_payload else None)
        campaign_name = context.get("campaign_name")
        interest = (
            context.get("interest")
            or (ctx.patient_metadata or {}).get("interest")
            or ("canetas" if lead_source == "weight_loss" else "consulta")
        )

        should_create = (
            lead_source in {"weight_loss", "campaign"}
            or convenio == "particular"
        )
        if not should_create:
            return

        notes_parts = [
            f"Agendado para {tool_input['date']} às {tool_input['hora_inicio'][:5]}",
            f"Convenio: {convenio}",
        ]
        if ctx.handoff_payload and ctx.handoff_payload.reason:
            notes_parts.append(f"Origem do handoff: {ctx.handoff_payload.reason}")
        if campaign_name:
            notes_parts.append(f"Campanha: {campaign_name}")

        await create_priority_lead(
            patient_id=ctx.patient_id,
            session_id=ctx.session_id,
            patient_name=tool_input.get("patient_name"),
            patient_phone=tool_input.get("patient_phone") or ctx.patient_phone,
            interest=interest,
            convenio=convenio,
            specialty=tool_input.get("specialty"),
            source_agent=lead_source or "scheduling",
            campaign_name=campaign_name,
            professional_id=professional.get("id"),
            professional_name=professional.get("nome"),
            notes=" | ".join(notes_parts),
            appointment_id=str(appointment.get("id")) if appointment.get("id") else None,
            conversation_history=ctx.conversation_history,
            metadata={
                "scheduled_date": tool_input.get("date"),
                "scheduled_time": tool_input.get("hora_inicio"),
                "lead_source": lead_source,
                "from_campaign": bool(campaign_name),
            },
        )
