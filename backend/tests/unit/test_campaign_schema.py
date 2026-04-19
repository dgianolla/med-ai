import sys
import unittest
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from campaigns.schema import (  # noqa: E402
    CampaignSchemaError,
    build_schema,
    lint,
)


def _fm(**overrides):
    base = {
        "campaign_name": "Checkup Teste",
    }
    base.update(overrides)
    return base


class BuildSchemaTest(unittest.TestCase):
    def test_minimal_valid_frontmatter_builds_schema(self):
        schema = build_schema(slug="checkup_teste", frontmatter=_fm(), body="conteudo suficiente para passar no linter de tamanho")
        self.assertEqual(schema.campaign_id, "checkup_teste")
        self.assertEqual(schema.campaign_name, "Checkup Teste")
        self.assertEqual(schema.status, "active")
        self.assertEqual(schema.handoff_target, "scheduling")
        self.assertEqual(schema.priority, 50)
        self.assertEqual(schema.allowed_promises, [])
        self.assertEqual(schema.forbidden_promises, [])

    def test_accepts_legacy_nome_alias(self):
        schema = build_schema(slug="x", frontmatter={"nome": "Campanha X"}, body="x" * 50)
        self.assertEqual(schema.campaign_name, "Campanha X")

    def test_accepts_legacy_valor_alias_as_offer_anchor(self):
        schema = build_schema(slug="x", frontmatter={"nome": "X", "valor": "R$ 100"}, body="x" * 50)
        self.assertEqual(schema.offer_anchor, "R$ 100")

    def test_missing_name_raises(self):
        with self.assertRaises(CampaignSchemaError):
            build_schema(slug="x", frontmatter={}, body="x" * 50)

    def test_invalid_status_raises(self):
        with self.assertRaises(CampaignSchemaError):
            build_schema(slug="x", frontmatter=_fm(status="archived"), body="x" * 50)

    def test_invalid_handoff_target_raises(self):
        with self.assertRaises(CampaignSchemaError):
            build_schema(slug="x", frontmatter=_fm(handoff_target="exams"), body="x" * 50)

    def test_invalid_date_raises(self):
        with self.assertRaises(CampaignSchemaError):
            build_schema(slug="x", frontmatter=_fm(valid_from="2026/01/01"), body="x" * 50)

    def test_priority_coerced_to_int(self):
        schema = build_schema(slug="x", frontmatter=_fm(priority="80"), body="x" * 50)
        self.assertEqual(schema.priority, 80)

    def test_invalid_priority_raises(self):
        with self.assertRaises(CampaignSchemaError):
            build_schema(slug="x", frontmatter=_fm(priority="urgent"), body="x" * 50)

    def test_list_frontmatter_preserved(self):
        schema = build_schema(
            slug="x",
            frontmatter=_fm(forbidden_promises=["a", "b"], allowed_promises=["c"]),
            body="x" * 50,
        )
        self.assertEqual(schema.forbidden_promises, ["a", "b"])
        self.assertEqual(schema.allowed_promises, ["c"])

    def test_string_falls_back_to_single_item_list(self):
        schema = build_schema(
            slug="x",
            frontmatter=_fm(forbidden_promises="valor único"),
            body="x" * 50,
        )
        self.assertEqual(schema.forbidden_promises, ["valor único"])


class IsActiveOnTest(unittest.TestCase):
    def test_paused_is_not_active(self):
        schema = build_schema(slug="x", frontmatter=_fm(status="paused"), body="x" * 50)
        self.assertFalse(schema.is_active_on(date(2026, 4, 19)))

    def test_before_valid_from_is_not_active(self):
        schema = build_schema(
            slug="x", frontmatter=_fm(valid_from="2026-06-01"), body="x" * 50,
        )
        self.assertFalse(schema.is_active_on(date(2026, 4, 19)))
        self.assertTrue(schema.is_active_on(date(2026, 6, 15)))

    def test_after_valid_until_is_not_active(self):
        schema = build_schema(
            slug="x", frontmatter=_fm(valid_until="2026-03-31"), body="x" * 50,
        )
        self.assertFalse(schema.is_active_on(date(2026, 4, 19)))
        self.assertTrue(schema.is_active_on(date(2026, 3, 15)))


class LintTest(unittest.TestCase):
    def test_clean_campaign_has_no_warnings(self):
        schema = build_schema(
            slug="x",
            frontmatter=_fm(),
            body=(
                "## Sobre a campanha\nTexto comercial de contexto. "
                "Inclui fluxo e etapas de atendimento detalhadas."
            ),
        )
        self.assertEqual(lint(schema), [])

    def test_behavioral_heading_is_warned(self):
        schema = build_schema(
            slug="x",
            frontmatter=_fm(),
            body=(
                "## Sobre a campanha\ntexto.\n\n## Tom\n"
                "Seja mais direto e formal nesta campanha."
            ),
        )
        warnings = lint(schema)
        self.assertTrue(any("comportamental" in w.lower() or "regra global" in w.lower() for w in warnings))

    def test_redefining_agent_identity_is_warned(self):
        schema = build_schema(
            slug="x",
            frontmatter=_fm(),
            body="## Sobre a campanha\nVocê é a LIA, assistente de vendas. Texto de fluxo.",
        )
        warnings = lint(schema)
        self.assertTrue(any("identidade" in w.lower() for w in warnings))

    def test_valid_until_before_valid_from_is_warned(self):
        schema = build_schema(
            slug="x",
            frontmatter=_fm(valid_from="2026-06-01", valid_until="2026-05-01"),
            body="x" * 50,
        )
        warnings = lint(schema)
        self.assertTrue(any("valid_until" in w for w in warnings))

    def test_short_body_is_warned(self):
        schema = build_schema(slug="x", frontmatter=_fm(), body="muito curto")
        warnings = lint(schema)
        self.assertTrue(any("curto" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
