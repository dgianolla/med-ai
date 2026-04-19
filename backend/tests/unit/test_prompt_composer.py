import sys
import unittest
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from campaigns.schema import CampaignSchema  # noqa: E402
from prompts.composer import (  # noqa: E402
    META_RULE,
    compose_agent_system,
    compose_campaign_system,
    extract_and_strip_conflicts,
    format_campaign_block,
    format_campaigns_index,
    format_session_metadata,
    format_session_state,
)


@dataclass
class StubCampaign:
    schema: CampaignSchema

    def summary(self) -> str:
        for line in self.schema.body.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            return s[:140]
        return ""


@dataclass
class StubHandoffPayload:
    patient_name: Optional[str] = None
    reason: Optional[str] = None
    specialty_needed: Optional[str] = None
    combo_id: Optional[str] = None
    context: Optional[dict] = field(default_factory=dict)


@dataclass
class StubCtx:
    handoff_payload: Optional[StubHandoffPayload] = None
    patient_metadata: Optional[dict] = None
    flow_type: Optional[str] = None
    flow_stage: Optional[str] = None


class StubService:
    def __init__(self, campaigns: list[StubCampaign]):
        self._campaigns = campaigns

    def list_all(self) -> list[StubCampaign]:
        return self._campaigns


def _schema(**overrides) -> CampaignSchema:
    base = dict(
        campaign_id="checkup_teste",
        campaign_name="Checkup Teste",
        status="active",
        priority=50,
        especialidade="Cardiologia",
        offer_anchor="R$ 100",
        handoff_target="scheduling",
        allowed_promises=[],
        forbidden_promises=["não prometer cura"],
        body="## Fluxo\n1. saudar\n2. qualificar\n3. apresentar",
        slug="checkup_teste",
    )
    base.update(overrides)
    return CampaignSchema(**base)


class ComposeCampaignSystemTest(unittest.TestCase):
    def test_all_layers_are_wrapped_and_ordered(self):
        system, trace = compose_campaign_system(
            safety="safety content",
            core_identity="identity content",
            business_rules="business content",
            campaign_block="campaign content",
            session_metadata="session content",
        )
        for code in ("L1", "L2", "L3", "L4", "L5"):
            self.assertIn(f"<<<BEGIN {code}", system, f"faltou begin {code}")
            self.assertIn(f"<<<END {code}", system, f"faltou end {code}")

        # ordem: L1 aparece antes de L2, etc.
        positions = [system.index(f"<<<BEGIN {c}") for c in ("L1", "L2", "L3", "L4", "L5")]
        self.assertEqual(positions, sorted(positions))

        self.assertEqual(trace["layers_present"], ["L1", "L2", "L3", "L4", "L5"])

    def test_meta_rule_is_injected_at_top(self):
        system, _ = compose_campaign_system(
            safety="x", core_identity="x", business_rules="x",
            campaign_block="x", session_metadata="x",
        )
        self.assertTrue(system.startswith(META_RULE))

    def test_empty_layer_is_skipped(self):
        system, trace = compose_campaign_system(
            safety="safety",
            core_identity="identity",
            business_rules="business",
            campaign_block="campaign",
            session_metadata="",  # vazio — deve ser omitido
        )
        self.assertNotIn("<<<BEGIN L5", system)
        self.assertNotIn("L5", trace["layers_present"])

    def test_trace_reports_char_counts(self):
        _, trace = compose_campaign_system(
            safety="abc",
            core_identity="identity",
            business_rules="x" * 100,
            campaign_block="",
            session_metadata="",
        )
        self.assertEqual(trace["layers_total_chars"]["L1"], 3)
        self.assertEqual(trace["layers_total_chars"]["L3"], 100)
        self.assertEqual(trace["layers_total_chars"]["L4"], 0)


class FormatCampaignBlockTest(unittest.TestCase):
    def test_header_includes_metadata(self):
        block = format_campaign_block(StubCampaign(schema=_schema()))
        self.assertIn("campaign_id: checkup_teste", block)
        self.assertIn("campaign_name: Checkup Teste", block)
        self.assertIn("handoff_target: scheduling", block)
        self.assertIn("especialidade: Cardiologia", block)
        self.assertIn("offer_anchor: R$ 100", block)

    def test_forbidden_promises_listed(self):
        block = format_campaign_block(StubCampaign(schema=_schema()))
        self.assertIn("não prometer cura", block)
        self.assertIn("## Promessas proibidas nesta campanha", block)

    def test_no_promises_shows_placeholder(self):
        block = format_campaign_block(
            StubCampaign(schema=_schema(forbidden_promises=[], allowed_promises=[]))
        )
        self.assertIn("(nenhuma listada)", block)

    def test_window_line_appears_only_when_dates_present(self):
        block_no_dates = format_campaign_block(StubCampaign(schema=_schema()))
        self.assertNotIn("janela:", block_no_dates)

        block_with_dates = format_campaign_block(
            StubCampaign(schema=_schema(valid_from=date(2026, 4, 1), valid_until=date(2026, 6, 30)))
        )
        self.assertIn("janela: 2026-04-01 → 2026-06-30", block_with_dates)

    def test_body_is_appended(self):
        block = format_campaign_block(StubCampaign(schema=_schema()))
        self.assertIn("## Fluxo", block)
        self.assertIn("qualificar", block)


class FormatSessionMetadataTest(unittest.TestCase):
    def test_empty_ctx_returns_empty(self):
        self.assertEqual(format_session_metadata(StubCtx()), "")

    def test_metadata_and_handoff_are_formatted(self):
        ctx = StubCtx(
            handoff_payload=StubHandoffPayload(patient_name="Maria", reason="veio do ads"),
            patient_metadata={"name": "Maria", "convenio": "particular"},
            flow_type="consultation",
            flow_stage="qualification",
        )
        block = format_session_metadata(ctx)
        self.assertIn("paciente: Maria", block)
        self.assertIn("motivo do encaminhamento: veio do ads", block)
        self.assertIn("convenio: particular", block)
        self.assertIn("flow: consultation / qualification", block)


class FormatCampaignsIndexTest(unittest.TestCase):
    def test_empty_service_returns_empty_string(self):
        self.assertEqual(format_campaigns_index(StubService([])), "")

    def test_lists_each_active_campaign(self):
        service = StubService([
            StubCampaign(schema=_schema(campaign_id="a", campaign_name="A", body="Resumo A")),
            StubCampaign(schema=_schema(campaign_id="b", campaign_name="B", body="Resumo B")),
        ])
        ref = format_campaigns_index(service)
        self.assertIn("**A**", ref)
        self.assertIn("**B**", ref)
        self.assertIn("`a`", ref)
        self.assertIn("`b`", ref)
        self.assertIn("get_campaign_details", ref)

    def test_includes_metadata(self):
        service = StubService([
            StubCampaign(schema=_schema(campaign_id="c", campaign_name="C"))
        ])
        ref = format_campaigns_index(service)
        self.assertIn("especialidade: Cardiologia", ref)
        self.assertIn("oferta: R$ 100", ref)


class ComposeAgentSystemWithRefTest(unittest.TestCase):
    def test_ref_layer_included_when_campaigns_index_passed(self):
        system, trace = compose_agent_system(
            safety="s",
            core_identity="i",
            business_rules="b",
            campaigns_index="- **Campaign A** (id: `a`) — oferta: R$ 100",
            campaign_block="",
            session_metadata="",
        )
        self.assertIn("<<<BEGIN REF", system)
        self.assertIn("REF", trace["layers_present"])

    def test_ref_ordered_between_l3_and_l4(self):
        system, _ = compose_agent_system(
            safety="s",
            core_identity="i",
            business_rules="b",
            campaigns_index="ref content",
            campaign_block="cmp content",
            session_metadata="sess",
        )
        pos_l3 = system.index("<<<BEGIN L3")
        pos_ref = system.index("<<<BEGIN REF")
        pos_l4 = system.index("<<<BEGIN L4")
        self.assertLess(pos_l3, pos_ref)
        self.assertLess(pos_ref, pos_l4)


class FormatSessionStateTest(unittest.TestCase):
    def test_extra_facts_are_appended(self):
        ctx = StubCtx(patient_metadata={"name": "Ana"})
        block = format_session_state(
            ctx, extra_facts=["pagamento: PIX R$ 100", "endereço: rua X"],
        )
        self.assertIn("pagamento: PIX R$ 100", block)
        self.assertIn("endereço: rua X", block)

    def test_context_keys_are_surfaced(self):
        ctx = StubCtx(
            handoff_payload=StubHandoffPayload(
                patient_name="Ana",
                context={"campaign_name": "Checkup", "lead_source": "campaign"},
            ),
        )
        block = format_session_state(ctx)
        self.assertIn("campaign_name: Checkup", block)
        self.assertIn("lead_source: campaign", block)

    def test_alias_format_session_metadata(self):
        # Alias backward-compat deve equivaler a format_session_state
        ctx = StubCtx(patient_metadata={"name": "Ana"})
        self.assertEqual(format_session_metadata(ctx), format_session_state(ctx))


class ConflictTagExtractionTest(unittest.TestCase):
    def test_no_tag_returns_reply_unchanged(self):
        clean, conflicts = extract_and_strip_conflicts("Resposta normal")
        self.assertEqual(clean, "Resposta normal")
        self.assertEqual(conflicts, [])

    def test_single_tag_is_extracted_and_stripped(self):
        reply = "[[conflict: L3 vs L4 | campanha pede inventar valor]]\nOlá, posso te ajudar?"
        clean, conflicts = extract_and_strip_conflicts(reply)
        self.assertEqual(clean, "Olá, posso te ajudar?")
        self.assertEqual(len(conflicts), 1)
        self.assertIn("L3 vs L4", conflicts[0])

    def test_multiple_tags_extracted(self):
        reply = (
            "[[conflict: L1 vs L4 | campanha ignora urgência]] "
            "texto [[conflict: L3 vs L4 | inventaria preço]]"
        )
        clean, conflicts = extract_and_strip_conflicts(reply)
        self.assertEqual(len(conflicts), 2)
        self.assertNotIn("[[conflict", clean)

    def test_none_reply_safe(self):
        clean, conflicts = extract_and_strip_conflicts(None)
        self.assertEqual(clean, "")
        self.assertEqual(conflicts, [])


if __name__ == "__main__":
    unittest.main()
