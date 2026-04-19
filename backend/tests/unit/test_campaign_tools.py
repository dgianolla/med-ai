"""Testes para tools/campaign_tools.py — list_active_campaigns, get_campaign_details."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from campaigns.schema import CampaignSchema  # noqa: E402
from campaigns.service import Campaign  # noqa: E402
from tools.campaign_tools import (  # noqa: E402
    CAMPAIGN_TOOL_NAMES,
    TOOLS,
    execute_campaign_tool,
    get_campaign_details,
    list_active_campaigns,
)


def _make_campaign(
    *,
    campaign_id: str = "checkup_teste",
    campaign_name: str = "Checkup Teste",
    especialidade: str = "Cardiologia",
    offer_anchor: str = "R$ 100",
    body: str = "## Fluxo\n1. saudar\n2. qualificar",
    allowed_promises: list[str] = None,
    forbidden_promises: list[str] = None,
) -> Campaign:
    schema = CampaignSchema(
        slug=campaign_id,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        status="active",
        priority=50,
        especialidade=especialidade,
        offer_anchor=offer_anchor,
        handoff_target="scheduling",
        allowed_promises=allowed_promises or [],
        forbidden_promises=forbidden_promises or [],
        body=body,
    )
    return Campaign(schema=schema, raw=body)


class CampaignToolsSchemaTest(unittest.TestCase):
    def test_tools_list_exposes_expected_names(self):
        names = {t["name"] for t in TOOLS}
        self.assertEqual(names, {"list_active_campaigns", "get_campaign_details"})

    def test_frozenset_matches_tools_list(self):
        names = {t["name"] for t in TOOLS}
        self.assertEqual(names, set(CAMPAIGN_TOOL_NAMES))

    def test_get_campaign_details_requires_campaign_id(self):
        tool = next(t for t in TOOLS if t["name"] == "get_campaign_details")
        self.assertIn("campaign_id", tool["input_schema"]["required"])


class ListActiveCampaignsTest(unittest.TestCase):
    def test_returns_count_and_summary(self):
        fake = [
            _make_campaign(campaign_id="a", campaign_name="A", body="Oferta A"),
            _make_campaign(campaign_id="b", campaign_name="B", body="Oferta B"),
        ]
        with patch("tools.campaign_tools.get_campaign_service") as svc_factory:
            svc_factory.return_value.list_all.return_value = fake
            result = list_active_campaigns()

        self.assertEqual(result["count"], 2)
        ids = [c["campaign_id"] for c in result["campaigns"]]
        self.assertEqual(ids, ["a", "b"])
        self.assertIn("summary", result["campaigns"][0])

    def test_empty_returns_zero(self):
        with patch("tools.campaign_tools.get_campaign_service") as svc_factory:
            svc_factory.return_value.list_all.return_value = []
            result = list_active_campaigns()
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["campaigns"], [])


class GetCampaignDetailsTest(unittest.TestCase):
    def test_returns_full_details_when_found(self):
        c = _make_campaign(
            campaign_id="checkup_teste",
            forbidden_promises=["não prometer cura"],
        )
        with patch("tools.campaign_tools.get_campaign_service") as svc_factory:
            svc_factory.return_value.list_all.return_value = [c]
            result = get_campaign_details("checkup_teste")

        self.assertEqual(result["campaign_id"], "checkup_teste")
        self.assertEqual(result["especialidade"], "Cardiologia")
        self.assertIn("não prometer cura", result["forbidden_promises"])
        self.assertIn("## Fluxo", result["body"])

    def test_missing_id_returns_error(self):
        result = get_campaign_details("")
        self.assertIn("error", result)

    def test_not_found_returns_error_and_available_ids(self):
        c = _make_campaign(campaign_id="a", campaign_name="A")
        with patch("tools.campaign_tools.get_campaign_service") as svc_factory:
            svc_factory.return_value.list_all.return_value = [c]
            result = get_campaign_details("xyz")

        self.assertIn("error", result)
        self.assertEqual(result["available_ids"], ["a"])


class ExecuteCampaignToolTest(unittest.TestCase):
    def test_dispatches_list(self):
        with patch("tools.campaign_tools.get_campaign_service") as svc_factory:
            svc_factory.return_value.list_all.return_value = []
            result = execute_campaign_tool("list_active_campaigns", {})
        self.assertEqual(result["count"], 0)

    def test_dispatches_get_details(self):
        c = _make_campaign(campaign_id="z", campaign_name="Z")
        with patch("tools.campaign_tools.get_campaign_service") as svc_factory:
            svc_factory.return_value.list_all.return_value = [c]
            result = execute_campaign_tool(
                "get_campaign_details", {"campaign_id": "z"}
            )
        self.assertEqual(result["campaign_id"], "z")

    def test_unknown_tool_returns_error(self):
        result = execute_campaign_tool("foo_bar", {})
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
