import logging
from anthropic import AsyncAnthropic

from config import get_settings
from db.models import SessionContext, AgentResult, HandoffPayload
from agents.base_agent import BaseAgent
from agents.prompt_loader import load_prompt
from knowledge.tools import TOOLS as KNOWLEDGE_TOOLS, get_clinic_info
from knowledge.service import get_knowledge

logger = logging.getLogger(__name__)

ALL_TOOLS = KNOWLEDGE_TOOLS

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
    model = "claude-haiku-4-5"

    async def run(self, ctx: SessionContext) -> AgentResult:
        settings = get_settings()
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        patient_name = (ctx.patient_metadata or {}).get("name", "Desconhecido")
        logger.info("[COMMERCIAL] Iniciando | patient=%s (%s)", patient_name, ctx.patient_phone)

        system = load_prompt("commercial")

        # Injeta informações dinâmicas da clínica
        knowledge = get_knowledge()
        payment_info = knowledge.get("clinic_info", "payment")
        if payment_info:
            system += (
                f"\n\n## FORMAS DE PAGAMENTO ATUALIZADAS\n"
                f"Métodos: {', '.join(payment_info.get('methods', []))}\n"
                f"Chave PIX: {payment_info.get('pix_key', 'N/A')}\n"
                f"Parcelamento: Consultas até {payment_info.get('installments', {}).get('consultas', '2x')} | "
                f"Exames/Combos até {payment_info.get('installments', {}).get('exames_combos', '10x')}"
            )

        address_info = knowledge.get("clinic_info", "address")
        if address_info:
            system += (
                f"\n\n## ENDEREÇO\n"
                f"{address_info.get('street')} — {address_info.get('landmark')}"
            )

        # Contexto do handoff (ex: veio de Exames com exames específicos)
        if ctx.handoff_payload:
            payload = ctx.handoff_payload
            if payload.patient_name:
                system += f"\n\nO paciente já se identificou como: {payload.patient_name}"
            if payload.reason:
                system += f"\nMotivo do encaminhamento: {payload.reason}"
            if payload.exam_ids:
                system += f"\nExames de interesse: {', '.join(payload.exam_ids)}"

        # Injeta contexto acumulado de handoffs anteriores
        if ctx.handoff_payload and ctx.handoff_payload.context:
            context = ctx.handoff_payload.context
            collected_info = []
            if context.get("convenio"):
                collected_info.append(f"Convênio: {context['convenio']}")
            if context.get("specialty"):
                collected_info.append(f"Especialidade de interesse: {context['specialty']}")
            if context.get("scheduled_date"):
                collected_info.append(f"Já possui agendamento em {context['scheduled_date']}")
            if context.get("previous_agent"):
                collected_info.append(f"Veio do agente: {context['previous_agent']}")
            if collected_info:
                system += "\n\n## CONTEXTO DA CONVERSA ANTERIOR\n" + "\n".join(collected_info)

        messages = self._build_history(ctx)

        # Loop agentico para suportar tools
        for _ in range(5):
            response = await client.messages.create(
                model=self.model,
                max_tokens=384,
                temperature=0.7,
                system=system,
                tools=ALL_TOOLS,
                messages=messages,
            )

            # Claude quer usar uma tool
            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})

                import json
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

            # Claude terminou — extrai resposta de texto
            reply = next(
                (b.text for b in response.content if hasattr(b, "text")),
                None,
            )
            break
        else:
            reply = None

        handoff_target = None
        handoff_payload = None
        patient_name = (ctx.patient_metadata or {}).get("name")
        done = False

        if reply:
            reply_lower = reply.lower()

            # Detecta se acabou de enviar info de checkup e deve handoff automático para exames
            is_checkup_response = any(kw in reply_lower for kw in [
                "checkup", "combo mulher", "combo homem", "combo idoso",
                "combo pediatria", "combo cardiologista", "r$ 279", "r$ 370",
                "r$ 489", "r$ 599", "r$ 464",
            ])

            if is_checkup_response:
                # Handoff invisível para o agente de exames
                handoff_target = "exams"
                handoff_payload = HandoffPayload(
                    type="to_exams",
                    patient_name=patient_name,
                    reason="Paciente recebeu info de checkup e será atendido pelo agente de exames",
                    context={
                        "auto_handoff_from_commercial": True,
                        "checkup_packages_sent": True,
                        **(ctx.handoff_payload.context if ctx.handoff_payload and ctx.handoff_payload.context else {}),
                    },
                )
                logger.info("[COMMERCIAL] Auto-handoff → exams (checkup) | patient=%s", patient_name)
            elif any(p in reply_lower for p in _SCHEDULING_HANDOFF_PHRASES):
                handoff_target = "scheduling"
                handoff_payload = HandoffPayload(
                    type="to_scheduling",
                    patient_name=patient_name,
                    reason="Paciente quer agendar consulta após atendimento comercial",
                )
                logger.info("[COMMERCIAL] Handoff → scheduling | patient=%s", patient_name)
            elif any(p in reply_lower for p in _DONE_PHRASES):
                done = True
                logger.info("[COMMERCIAL] Sessão encerrada | patient=%s", patient_name)

        logger.info(
            "[COMMERCIAL] Resposta | patient=%s | handoff=%s | done=%s",
            patient_name, handoff_target or "Nenhum", done,
        )

        return AgentResult(
            reply=reply,
            handoff_target=handoff_target,
            handoff_payload=handoff_payload,
            done=done,
        )
