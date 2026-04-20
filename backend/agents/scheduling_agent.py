import json
import logging
from anthropic import AsyncAnthropic
from anthropic import APIStatusError

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
from tools.scheduling_tools import TOOLS
from tools.campaign_tools import (
    TOOLS as CAMPAIGN_TOOLS,
    CAMPAIGN_TOOL_NAMES,
    execute_campaign_tool,
)
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
from time_utils import clinic_now, format_date_br, weekday_name_pt_br

logger = logging.getLogger(__name__)

ALL_TOOLS = TOOLS + KNOWLEDGE_TOOLS + CAMPAIGN_TOOLS


def _short(text: str | None, limit: int = 120) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _knowledge_facts() -> list[str]:
    """Snapshot de dados dinâmicos da clínica para L5."""
    knowledge = get_knowledge()
    facts: list[str] = []

    payment = knowledge.get("clinic_info", "payment")
    if payment:
        installments = payment.get("installments", {})
        facts.append(
            f"pagamento: métodos={', '.join(payment.get('methods', []))} | "
            f"PIX={payment.get('pix_key', 'N/A')} | "
            f"consultas até {installments.get('consultas', '2x')} | "
            f"exames/combos até {installments.get('exames_combos', '10x')}"
        )

    arrival = knowledge.get("clinic_info", "arrival_policy")
    if arrival:
        facts.append(
            f"chegada: {arrival.get('arrive_minutes_before', 15)}min antes | "
            f"tolerância: {arrival.get('tolerance_minutes', 15)}min"
        )

    return facts


def _combo_facts(ctx: SessionContext) -> list[str]:
    """Fatos adicionais para L5 quando há combo em curso."""
    if not (ctx.handoff_payload and ctx.handoff_payload.combo_id):
        return []
    combo_ctx = ctx.handoff_payload.context or {}
    combo_name = combo_ctx.get("combo_name", ctx.handoff_payload.combo_id)
    facts = [
        f"combo fechado: {combo_name} (id: {ctx.handoff_payload.combo_id}) — "
        "agendar apenas a ETAPA DE CONSULTA; especialidade já resolvida pelo combo",
    ]
    if combo_ctx.get("collection_schedule_required"):
        facts.append(
            "combo tem etapa de COLETA separada — não agendar coleta aqui, só consulta"
        )
    if not combo_ctx.get("convenio"):
        facts.append("combos são sempre particular — não perguntar convênio")
    return facts


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

        now = clinic_now()
        core_identity = load_prompt("scheduling").format(
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

        extra_facts = _knowledge_facts() + _combo_facts(ctx)
        session_metadata = format_session_state(ctx, extra_facts=extra_facts)

        system, trace = compose_agent_system(
            safety=load_prompt("_safety"),
            core_identity=core_identity,
            business_rules=load_prompt("_business_rules"),
            campaigns_index=format_campaigns_index(service),
            campaign_block=campaign_block,
            session_metadata=session_metadata,
        )
        logger.info(
            "[SCHEDULING] Trace | patient=%s | layers=%s | campaign_id=%s",
            patient_name, trace["layers_present"], campaign_id,
        )

        for _ in range(10):
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
            except Exception:
                logger.exception(
                    "[SCHEDULING] Unexpected provider failure | patient=%s | messages=%s",
                    patient_name,
                    len(messages),
                )
                return AgentResult(
                    reply="Desculpe, tive um problema interno ao continuar seu agendamento. Pode me dizer novamente qual especialidade ou exame você quer agendar?",
                )

            if response.stop_reason == "tool_use":
                tool_names = [block.name for block in response.content if getattr(block, "type", None) == "tool_use"]
                logger.info(
                    "[SCHEDULING] Tool request | patient=%s | tools=%s",
                    patient_name,
                    tool_names,
                )
                messages.append({"role": "assistant", "content": response.content})

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
                        appointment_data = result.get("agendamento", {})
                        if appointment_data.get("id"):
                            ctx.patient_metadata["appointment_id"] = appointment_data["id"]

                messages.append({"role": "user", "content": tool_results})
                continue

            reply = next(
                (b.text for b in response.content if hasattr(b, "text")),
                None,
            )

            reply, conflicts = extract_and_strip_conflicts(reply)
            if conflicts:
                logger.warning(
                    "[SCHEDULING] Conflict | patient=%s | conflicts=%s",
                    patient_name, conflicts,
                )

            done = (
                reply and
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
                reply=reply or None,
                session_updates=ctx.patient_metadata,
                done=bool(done),
            )

        return AgentResult(
            reply="Desculpe, tive um problema ao processar sua solicitação. Por favor, tente novamente.",
        )

    async def _execute_tool(self, tool_name: str, tool_input: dict, ctx: SessionContext) -> dict:
        try:
            if tool_name in CAMPAIGN_TOOL_NAMES:
                return execute_campaign_tool(tool_name, tool_input)

            if tool_name == "get_clinic_info":
                return await get_clinic_info(tool_input["query"])

            if tool_name == "get_agenda":
                agenda = await get_agenda(tool_input["date_start"], tool_input["date_end"])
                professional_id = tool_input["professional_id"]
                prof_agenda = [a for a in agenda if a.get("profissionalSaude", {}).get("id") == professional_id]
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
                            "data_br": format_date_br(d),
                            "dia_semana": weekday_name_pt_br(d),
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
