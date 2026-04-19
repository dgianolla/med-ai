"""Testes end-to-end leves do loader: parse real dos .md em /campaigns.

Executam contra os arquivos reais do diretório — servem como snapshot/guard
para pegar regressão quando alguém migra o schema sem atualizar uma campanha.
"""

import sys
import unittest
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from campaigns.service import CampaignService, _parse_frontmatter  # noqa: E402


class ParseFrontmatterTest(unittest.TestCase):
    def test_inline_list(self):
        raw = "---\nforbidden_promises: [\"a\", \"b\"]\n---\ncorpo"
        fm, body = _parse_frontmatter(raw)
        self.assertEqual(fm["forbidden_promises"], ["a", "b"])
        self.assertEqual(body.strip(), "corpo")

    def test_block_list(self):
        raw = "---\nforbidden_promises:\n  - \"a\"\n  - \"b\"\nnome: X\n---\ncorpo"
        fm, _ = _parse_frontmatter(raw)
        self.assertEqual(fm["forbidden_promises"], ["a", "b"])
        self.assertEqual(fm["nome"], "X")

    def test_simple_key_value(self):
        raw = "---\nnome: Campanha\nvalor: R$ 100\n---\ncorpo"
        fm, _ = _parse_frontmatter(raw)
        self.assertEqual(fm["nome"], "Campanha")
        self.assertEqual(fm["valor"], "R$ 100")

    def test_comments_ignored(self):
        raw = "---\n# isto é comentário\nnome: X\n---\ncorpo"
        fm, _ = _parse_frontmatter(raw)
        self.assertEqual(fm["nome"], "X")
        self.assertNotIn("# isto é comentário", fm)

    def test_no_frontmatter_returns_empty_fm(self):
        raw = "sem frontmatter\napenas corpo"
        fm, body = _parse_frontmatter(raw)
        self.assertEqual(fm, {})
        self.assertEqual(body, raw)


class CampaignServiceLoadTest(unittest.TestCase):
    """Carrega os .md reais e valida estrutura."""

    def setUp(self):
        self.service = CampaignService(today_provider=lambda: date(2026, 4, 19))

    def test_loads_all_real_campaign_files_without_errors(self):
        campaigns = self.service.list_loaded()
        self.assertGreater(len(campaigns), 0, "Esperava ao menos uma campanha carregada")
        for c in campaigns:
            self.assertTrue(c.schema.campaign_id, f"campaign_id vazio em {c.slug}")
            self.assertTrue(c.schema.campaign_name, f"campaign_name vazio em {c.slug}")
            self.assertIn(c.schema.status, {"active", "paused", "draft"})
            self.assertIn(c.schema.handoff_target, {"scheduling", "commercial", "human", "none"})

    def test_list_all_returns_only_active(self):
        active = self.service.list_all()
        for c in active:
            self.assertTrue(c.schema.is_active_on(date(2026, 4, 19)))

    def test_get_returns_campaign_by_exact_name_case_insensitive(self):
        campaigns = self.service.list_loaded()
        self.assertGreater(len(campaigns), 0)
        sample = campaigns[0]
        fetched = self.service.get(sample.nome.upper())
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.campaign_id, sample.campaign_id)

    def test_get_returns_none_for_paused_campaign(self):
        service = CampaignService(today_provider=lambda: date(2026, 4, 19))
        service._load_all()
        campaigns = list(service._cache_all.values())
        if campaigns:
            # força a primeira a paused no cache em memória só para o teste
            campaigns[0].schema.status = "paused"
            self.assertIsNone(service.get(campaigns[0].nome))

    def test_index_text_nonempty_when_campaigns_active(self):
        text = self.service.index_text()
        self.assertIn("CAMPANHAS ATIVAS", text)


if __name__ == "__main__":
    unittest.main()
