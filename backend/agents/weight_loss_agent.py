import json
import logging
from datetime import datetime
from anthropic import AsyncAnthropic

from config import get_settings
from db.models import SessionContext, AgentResult, HandoffPayload
from agents.base_agent import BaseAgent
from agents.prompt_loader import load_prompt
from knowledge.tools import TOOLS as KNOWLEDGE_TOOLS, get_clinic_info
from knowledge.service import get_knowledge
from services.priority_leads import has_endocrino_availability, create_priority_lead

logger = logging.getLogger(__name__)

# Janela de dias úteis em que consideramos a agenda do endócrino "OK".
# Se não tiver vaga até aí, o lead vai pra fila de encaixe manual.
ENDOCRINO_AVAILABILITY_WINDOW_DAYS = 5

# Mensagem padrão quando o lead vai pra fila de encaixe.
# Não expõe que a agenda está cheia nem que existe uma "fila".
PRIORITY_QUEUE_MESSAGE = (
    "Por conta da alta procura por esse tratamento, nossa equipe comercial vai "
    "entrar em contato com você o quanto antes para confirmar os melhores horários "
    "e te dar todas as orientações. Pode aguardar nosso retorno."
)

ALL_TOOLS = KNOWLEDGE_TOOLS

_SCHEDULING_HANDOFF_PHRASES = [
    "vou te encaminhar para agendamento",
    "vou te encaminhar pro agendamento",
    "vou te passar pro agendamento",
    "vou te passar para agendamento",
    "te encaminhar para a agenda",
]

_DONE_PHRASES = [
    "qualquer dúvida, é só chamar",
    "qualquer coisa, me avisa",
    "fico à disposição",
]

_INTEREST_KEYWORDS = {
    "ozempic": ["ozempic", "semaglutida"],
    "mounjaro": ["mounjaro", "tirzepatida"],
}

_OBJECTION_KEYWORDS = {
    "preço": ["caro", "preço", "preco", "valor", "dinheiro", "parcel", "barato"],
    "medo": ["efeito colateral", "seguro", "risco", "medo", "preocupa"],
    "pensar": ["vou pensar", "depois", "talvez", "mais tarde"],
}


class WeightLossAgent(BaseAgent):
    """
    Agente dedicado a leads do protocolo de canetas injetáveis (Ozempic / Mounjaro).
    Qualifica o lead, esclarece com transparência, derruba objeção e converte
    para consulta com endocrinologista (Dr. Arthur Wagner).
    """

    agent_type = "weight_loss"
    model = "claude-sonnet-4-6"

    async def run(self, ctx: SessionContext) -> AgentResult:
        settings = get_settings()
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        patient_name = (ctx.patient_metadata or {}).get("name", "Desconhecido")
        logger.info("[WEIGHT_LOSS] Iniciando | patient=%s (%s)", patient_name, ctx.patient_phone)

        now = datetime.now()
        system = load_prompt("weight_loss").format(today=now.strftime("%Y-%m-%d"))

        knowledge = get_knowledge()
        payment_info = knowledge.get("clinic_info", "payment")
        if payment_info:
            installments = payment_info.get("installments", {})
            system += (
                f"\n\n## PAGAMENTO (dados atualizados)\n"
                f"Métodos: {', '.join(payment_info.get('methods', []))}\n"
                f"PIX: {payment_info.get('pix_key', 'N/A')}\n"
                f"Parcelamento de exames/protocolos: até {installments.get('exames_combos', '10x')} sem juros"
            )

        if ctx.handoff_payload:
            payload = ctx.handoff_payload
            if payload.patient_name:
                system += f"\n\nPaciente: {payload.patient_name}"
            if payload.reason:
                system += f"\nMotivo do encaminhamento: {payload.reason}"
            ctx_extra = payload.context or {}
            if ctx_extra.get("previous_agent"):
                system += f"\nVeio do agente: {ctx_extra['previous_agent']}"

        if ctx.patient_metadata:
            meta_lines = []
            for k in ("caneta_interesse", "ja_usou_caneta", "objection", "ready_for_consult"):
                if ctx.patient_metadata.get(k):
                    meta_lines.append(f"{k}: {ctx.patient_metadata[k]}")
            if meta_lines:
                system += "\n\n## METADATA DO LEAD\n" + "\n".join(meta_lines)

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

        # Detecta lead metadata a partir da última mensagem do paciente
        last_user_msg = next(
            (m["content"] for m in reversed(ctx.conversation_history) if m.get("role") == "user"),
            "",
        ).lower()

        session_updates: dict = {"interest": "canetas"}
        for caneta, kws in _INTEREST_KEYWORDS.items():
            if any(kw in last_user_msg for kw in kws):
                session_updates["caneta_interesse"] = caneta
                break
        for objection, kws in _OBJECTION_KEYWORDS.items():
            if any(kw in last_user_msg for kw in kws):
                session_updates["objection"] = objection
                break

        handoff_target = None
        handoff_payload = None
        done = False

        if reply:
            reply_lower = reply.lower()

            if any(p in reply_lower for p in _SCHEDULING_HANDOFF_PHRASES):
                # Antes de mandar pro scheduling, verifica se o endócrino tem
                # vaga real nos próximos dias. Se não, lead vai pra fila de
                # encaixe e o reply é substituído pela mensagem oficial.
                has_slot = await has_endocrino_availability(ENDOCRINO_AVAILABILITY_WINDOW_DAYS)
                logger.info(
                    "[WEIGHT_LOSS] Checagem de agenda do endócrino | patient=%s | tem_vaga=%s",
                    patient_name, has_slot,
                )

                if has_slot:
                    handoff_target = "scheduling"
                    handoff_payload = HandoffPayload(
                        type="to_scheduling",
                        patient_name=(ctx.patient_metadata or {}).get("name"),
                        reason="Lead de canetas injetáveis encaminhado para consulta com endocrinologista",
                        specialty_needed="Endocrinologia e Metabologia",
                        context={
                            "specialty": "Endocrinologia e Metabologia",
                            "professional_id": 30319,
                            "professional_name": "Dr. Arthur Wagner",
                            "esp_id": 19,
                            "lead_source": "weight_loss",
                            "interest": "canetas",
                            **{k: v for k, v in session_updates.items() if v},
                            **((ctx.handoff_payload.context if ctx.handoff_payload and ctx.handoff_payload.context else {})),
                        },
                    )
                    session_updates["ready_for_consult"] = "sim"
                    logger.info("[WEIGHT_LOSS] Handoff → scheduling (endócrino) | patient=%s", patient_name)
                else:
                    # Sem vaga → entra na fila de encaixe prioritário
                    notes_parts = []
                    if session_updates.get("caneta_interesse"):
                        notes_parts.append(f"Interesse: {session_updates['caneta_interesse']}")
                    if session_updates.get("objection"):
                        notes_parts.append(f"Objeção: {session_updates['objection']}")
                    if last_user_msg:
                        notes_parts.append(f"Última msg: {last_user_msg[:200]}")

                    await create_priority_lead(
                        patient_id=ctx.patient_id,
                        session_id=ctx.session_id,
                        patient_name=(ctx.patient_metadata or {}).get("name") or patient_name,
                        patient_phone=ctx.patient_phone,
                        interest="canetas",
                        specialty="Endocrinologia e Metabologia",
                        source_agent="weight_loss",
                        caneta_preferida=session_updates.get("caneta_interesse"),
                        professional_id=30319,
                        professional_name="Dr. Arthur Wagner",
                        notes=" | ".join(notes_parts) if notes_parts else None,
                        conversation_history=ctx.conversation_history,
                        metadata={
                            "ready_for_consult": "encaixe",
                            "objection": session_updates.get("objection"),
                        },
                    )

                    # Substitui o reply do LLM pela mensagem oficial — não
                    # expomos "agenda cheia" nem "fila", só "alta procura".
                    reply = PRIORITY_QUEUE_MESSAGE
                    session_updates["ready_for_consult"] = "encaixe"
                    session_updates["status"] = "priority_queue"
                    done = True
                    logger.info(
                        "[WEIGHT_LOSS] Lead → fila de encaixe prioritário | patient=%s",
                        patient_name,
                    )
            elif any(p in reply_lower for p in _DONE_PHRASES):
                done = True
                logger.info("[WEIGHT_LOSS] Sessão encerrada | patient=%s", patient_name)

        logger.info(
            "[WEIGHT_LOSS] Resposta | patient=%s | handoff=%s | done=%s | meta=%s",
            patient_name, handoff_target or "Nenhum", done, session_updates,
        )

        return AgentResult(
            reply=reply,
            handoff_target=handoff_target,
            handoff_payload=handoff_payload,
            session_updates=session_updates,
            done=done,
        )
