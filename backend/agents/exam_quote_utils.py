from db.models import HandoffPayload, SessionContext

EXAM_QUOTE_NOTE = "Paciente necessita fazer orçamento de exames."


def wants_exam_quote(message: str) -> bool:
    normalized = (message or "").lower()
    return any(
        term in normalized
        for term in ("orçamento", "orcamento", "valor", "quanto fica", "quanto custa", "preço", "preco")
    )


def has_exam_order(ctx: SessionContext, message: str) -> bool:
    normalized = (message or "").lower()
    return bool(ctx.exam_content) or any(
        term in normalized
        for term in ("pedido médico", "pedido medico", "pedido", "guia", "solicitação", "solicitacao", "[image]")
    )


def recent_history_indicates_exam_quote(ctx: SessionContext) -> bool:
    recent_messages = [
        (msg.get("content") or "").lower()
        for msg in ctx.conversation_history[-6:]
        if msg.get("role") == "user"
    ]
    return any(wants_exam_quote(content) for content in recent_messages)


def has_exam_quote_handoff_context(ctx: SessionContext) -> bool:
    payload = ctx.handoff_payload
    if not payload:
        return False
    context = payload.context or {}
    reason = (payload.reason or "").lower()
    return (
        context.get("human_handoff_type") == "exam_quote"
        or context.get("previous_agent") == "exams"
        or "orçamento de exames" in reason
        or "orcamento de exames" in reason
        or "agente de exames" in reason
    )


def build_exam_quote_handoff(
    ctx: SessionContext,
    *,
    patient_name: str | None,
    previous_agent: str,
    handoff_type: str = "to_commercial",
    human_tag: str = "Comercial",
) -> HandoffPayload:
    context = {
        "human_handoff": True,
        "human_handoff_type": "exam_quote",
        "human_tag": human_tag,
        "human_note": EXAM_QUOTE_NOTE,
        "human_complete_session": False,
        "invisible_handoff": True,
        "previous_agent": previous_agent,
    }
    if ctx.handoff_payload and ctx.handoff_payload.context:
        context = {**ctx.handoff_payload.context, **context}

    return HandoffPayload(
        type=handoff_type,
        patient_name=patient_name,
        reason=EXAM_QUOTE_NOTE,
        exam_content=ctx.exam_content if isinstance(ctx.exam_content, str) else None,
        context=context,
    )
