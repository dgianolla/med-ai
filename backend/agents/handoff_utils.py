from db.models import HandoffPayload, SessionContext


def previous_context(ctx: SessionContext) -> dict:
    if ctx.handoff_payload and ctx.handoff_payload.context:
        return dict(ctx.handoff_payload.context)
    return {}


def set_consultation_flow(ctx: SessionContext) -> None:
    ctx.flow_type = "consultation"
    ctx.flow_stage = None
    ctx.combo_id = None


def set_combo_flow(ctx: SessionContext, combo_id: str) -> None:
    ctx.flow_type = "combo"
    ctx.flow_stage = "waiting_consultation_schedule"
    ctx.combo_id = combo_id


def build_consultation_scheduling_handoff(
    ctx: SessionContext,
    *,
    patient_name: str | None,
    reason: str,
    source_agent: str,
    specialty_needed: str | None = None,
    extra_context: dict | None = None,
    invisible: bool = True,
) -> HandoffPayload:
    context = {
        "offer_type": "consultation",
        "flow_type": "consultation",
        "previous_agent": source_agent,
        **previous_context(ctx),
    }
    if invisible:
        context["invisible_handoff"] = True
    if extra_context:
        context.update(extra_context)

    return HandoffPayload(
        type="to_scheduling",
        patient_name=patient_name,
        reason=reason,
        specialty_needed=specialty_needed,
        context=context,
    )


def build_combo_scheduling_handoff(
    ctx: SessionContext,
    *,
    patient_name: str | None,
    reason: str,
    source_agent: str,
    combo: dict,
    extra_context: dict | None = None,
    invisible: bool = True,
) -> HandoffPayload:
    context = {
        "offer_type": "combo",
        "flow_type": "combo",
        "combo_id": combo["combo_id"],
        "combo_name": combo["name"],
        "collection_included": combo["collection_included"],
        "collection_schedule_required": combo["collection_schedule_required"],
        "previous_agent": source_agent,
        **previous_context(ctx),
    }
    if invisible:
        context["invisible_handoff"] = True
    if extra_context:
        context.update(extra_context)

    return HandoffPayload(
        type="to_scheduling",
        patient_name=patient_name,
        reason=reason,
        specialty_needed=combo["consultation_specialty"],
        combo_id=combo["combo_id"],
        context=context,
    )
