import sys
import unittest
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

supabase_stub = ModuleType("supabase")
supabase_stub.acreate_client = None
supabase_stub.AsyncClient = object
sys.modules.setdefault("supabase", supabase_stub)

db_package = ModuleType("db")
db_package.__path__ = [str(BACKEND_DIR / "db")]
sys.modules.setdefault("db", db_package)

models_module = ModuleType("db.models")


@dataclass
class HandoffPayload:
    type: str
    patient_name: str | None = None
    reason: str | None = None
    specialty_needed: str | None = None
    combo_id: str | None = None
    context: dict | None = None


@dataclass
class SessionContext:
    session_id: str
    patient_phone: str
    wts_session_id: str
    created_at: datetime
    last_activity_at: datetime
    handoff_payload: HandoffPayload | None = None
    flow_type: str | None = None
    flow_stage: str | None = None
    combo_id: str | None = None


models_module.HandoffPayload = HandoffPayload
models_module.SessionContext = SessionContext
sys.modules["db.models"] = models_module

from agents.handoff_utils import (  # noqa: E402
    DONE_PHRASES,
    SCHEDULING_HANDOFF_PHRASES,
    build_combo_scheduling_handoff,
    build_consultation_scheduling_handoff,
    matches_any_phrase,
    set_combo_flow,
    set_consultation_flow,
)
from db.models import HandoffPayload, SessionContext  # noqa: E402


def make_ctx() -> SessionContext:
    now = datetime.now()
    return SessionContext(
        session_id="session-1",
        patient_phone="5511999999999",
        wts_session_id="wts-1",
        created_at=now,
        last_activity_at=now,
    )


class HandoffUtilsTest(unittest.TestCase):
    def test_build_combo_scheduling_handoff_preserves_and_enriches_context(self) -> None:
        ctx = make_ctx()
        ctx.handoff_payload = HandoffPayload(
            type="to_campaign",
            context={
                "campaign_name": "Checkup Executivo",
                "lead_source": "campaign",
                "existing": "value",
            },
        )

        handoff = build_combo_scheduling_handoff(
            ctx,
            patient_name="Maria",
            reason="Combo confirmado",
            source_agent="campaign",
            combo={
                "combo_id": "combo_mulher_exames",
                "name": "Combo Mulher com Exames",
                "consultation_specialty": "ginecologia",
                "collection_included": True,
                "collection_schedule_required": True,
            },
            extra_context={"offer_type": "combo", "new_key": "new-value"},
        )

        self.assertEqual(handoff.type, "to_scheduling")
        self.assertEqual(handoff.patient_name, "Maria")
        self.assertEqual(handoff.combo_id, "combo_mulher_exames")
        self.assertEqual(handoff.specialty_needed, "ginecologia")
        self.assertEqual(handoff.context["flow_type"], "combo")
        self.assertEqual(handoff.context["offer_type"], "combo")
        self.assertEqual(handoff.context["combo_name"], "Combo Mulher com Exames")
        self.assertTrue(handoff.context["collection_schedule_required"])
        self.assertEqual(handoff.context["existing"], "value")
        self.assertEqual(handoff.context["new_key"], "new-value")
        self.assertEqual(handoff.context["previous_agent"], "campaign")
        self.assertTrue(handoff.context["invisible_handoff"])

    def test_build_consultation_scheduling_handoff_sets_default_contract(self) -> None:
        ctx = make_ctx()

        handoff = build_consultation_scheduling_handoff(
            ctx,
            patient_name="João",
            reason="Paciente quer agendar",
            source_agent="commercial",
            specialty_needed="cardiologia",
            extra_context={"lead_source": "campaign"},
        )

        self.assertEqual(handoff.type, "to_scheduling")
        self.assertEqual(handoff.patient_name, "João")
        self.assertEqual(handoff.specialty_needed, "cardiologia")
        self.assertIsNone(handoff.combo_id)
        self.assertEqual(handoff.context["flow_type"], "consultation")
        self.assertEqual(handoff.context["offer_type"], "consultation")
        self.assertEqual(handoff.context["previous_agent"], "commercial")
        self.assertEqual(handoff.context["lead_source"], "campaign")
        self.assertTrue(handoff.context["invisible_handoff"])

    def test_flow_helpers_update_session_context(self) -> None:
        ctx = make_ctx()
        ctx.flow_stage = "product_confirmed"
        ctx.combo_id = "combo_antigo"

        set_consultation_flow(ctx)
        self.assertEqual(ctx.flow_type, "consultation")
        self.assertIsNone(ctx.combo_id)
        self.assertIsNone(ctx.flow_stage)

        set_combo_flow(ctx, "combo_homem")
        self.assertEqual(ctx.flow_type, "combo")
        self.assertEqual(ctx.flow_stage, "waiting_consultation_schedule")
        self.assertEqual(ctx.combo_id, "combo_homem")


class MatchesAnyPhraseTest(unittest.TestCase):
    def test_exact_phrase(self):
        self.assertTrue(
            matches_any_phrase(
                "Vou te encaminhar para agendamento.",
                SCHEDULING_HANDOFF_PHRASES,
            )
        )

    def test_accents_ignored(self):
        self.assertTrue(
            matches_any_phrase(
                "Vou te passar pró agendamento.",
                SCHEDULING_HANDOFF_PHRASES,
            )
        )

    def test_uppercase_ignored(self):
        self.assertTrue(
            matches_any_phrase(
                "VOU TE ENCAMINHAR PARA AGENDAMENTO",
                SCHEDULING_HANDOFF_PHRASES,
            )
        )

    def test_embedded_in_longer_text(self):
        self.assertTrue(
            matches_any_phrase(
                "Perfeito, Maria! Vou te encaminhar para agendamento agora.",
                SCHEDULING_HANDOFF_PHRASES,
            )
        )

    def test_variant_agenda(self):
        self.assertTrue(
            matches_any_phrase("Vou te encaminhar para a agenda.", SCHEDULING_HANDOFF_PHRASES)
        )

    def test_no_match_returns_false(self):
        self.assertFalse(
            matches_any_phrase("Posso ajudar em algo mais?", SCHEDULING_HANDOFF_PHRASES)
        )

    def test_empty_text_returns_false(self):
        self.assertFalse(matches_any_phrase("", SCHEDULING_HANDOFF_PHRASES))
        self.assertFalse(matches_any_phrase(None, SCHEDULING_HANDOFF_PHRASES))

    def test_done_phrase_with_accents(self):
        self.assertTrue(matches_any_phrase("Fico à disposição!", DONE_PHRASES))
        self.assertTrue(matches_any_phrase("Até logo 👋", DONE_PHRASES))


if __name__ == "__main__":
    unittest.main()
