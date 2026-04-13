from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime


# ============================================================
# Tipos de agentes
# ============================================================
AgentType = Literal["triage", "scheduling", "exams", "commercial", "return", "cancellation", "weight_loss", "campaign"]

# ============================================================
# Payload de handoff entre agentes
# ============================================================
class HandoffPayload(BaseModel):
    type: Literal[
        "to_scheduling",
        "to_exams",
        "to_commercial",
        "to_return",
        "to_triage",
        "to_weight_loss",
        "to_campaign",
    ]
    patient_name: Optional[str] = None
    reason: Optional[str] = None
    exam_ids: Optional[list[str]] = None
    exam_prices: Optional[dict[str, float]] = None
    last_consult_date: Optional[str] = None
    specialty_needed: Optional[str] = None
    exam_order_code: Optional[str] = None
    exam_content: Optional[str] = None  # conteúdo extraído de imagem/PDF
    context: Optional[dict] = None  # dados arbitrários coletados pelo agente anterior
                                    # ex: {"convenio": "particular", "specialty": "cardiologia", "patient_phone": "..."}
                                    # pode incluir "appointment_id" para cancelamentos

# ============================================================
# Mensagem normalizada (entrada de qualquer tipo de mídia)
# ============================================================
MessageType = Literal["text", "audio", "image", "pdf", "file"]

class IncomingMessage(BaseModel):
    wts_session_id: str           # sessionId do wts.chat — usado para enviar resposta
    wts_message_id: str           # id da lastMessage — usado como refId
    patient_phone: str            # normalizado: ex "5511988579353"
    patient_name: Optional[str]
    wts_contact_id: str
    message_type: MessageType
    text: str                     # texto final (já transcrito/extraído se era mídia)
    file_url: Optional[str] = None
    received_at: datetime

# ============================================================
# Contexto de sessão (armazenado no Redis)
# ============================================================
class SessionContext(BaseModel):
    session_id: str               # phone_timestamp ex: "5511988579353_1711234567"
    patient_id: Optional[str] = None  # UUID do paciente no Supabase
    patient_phone: str
    wts_session_id: str
    current_agent: AgentType = "triage"
    conversation_history: list[dict] = []   # últimas 15 mensagens
    handoff_payload: Optional[HandoffPayload] = None
    patient_metadata: Optional[dict] = None # nome, cpf, convenio, etc coletados
    exam_content: Optional[str] = None      # conteúdo de exame enviado por mídia
    created_at: datetime
    last_activity_at: datetime

# ============================================================
# Resultado retornado por cada agente
# ============================================================
class AgentResult(BaseModel):
    reply: Optional[str] = None             # None para Triagem
    handoff_target: Optional[AgentType] = None
    handoff_payload: Optional[HandoffPayload] = None
    session_updates: Optional[dict] = None  # dados novos coletados (nome, etc)
    done: bool = False                      # sessão encerrada
