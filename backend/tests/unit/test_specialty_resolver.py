"""Testes para get_professionals_for_specialty — normalização + fallback por substring."""

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from integrations.scheduling_api import (  # noqa: E402
    PROFESSIONALS,
    _normalize_specialty,
    get_professionals_for_specialty,
)


class NormalizeTest(unittest.TestCase):
    def test_removes_accents_and_lowercases(self):
        self.assertEqual(_normalize_specialty("Endocrinologia"), "endocrinologia")
        self.assertEqual(_normalize_specialty("Saúde Metabólica"), "saude metabolica")
        self.assertEqual(_normalize_specialty("GINECOLOGIA"), "ginecologia")

    def test_collapses_punctuation_and_spaces(self):
        self.assertEqual(
            _normalize_specialty("Endocrinologia / Saúde Metabólica"),
            "endocrinologia saude metabolica",
        )
        self.assertEqual(
            _normalize_specialty("   Clínica   Geral  "),
            "clinica geral",
        )

    def test_empty_returns_empty(self):
        self.assertEqual(_normalize_specialty(""), "")
        self.assertEqual(_normalize_specialty(None), "")


class GetProfessionalsTest(unittest.TestCase):
    def test_exact_canonical_key(self):
        result = get_professionals_for_specialty("endocrinologia")
        self.assertEqual(result, PROFESSIONALS["endocrinologia"])

    def test_uppercase_with_accent(self):
        result = get_professionals_for_specialty("Ginecologia")
        self.assertEqual(result, PROFESSIONALS["ginecologia"])

    def test_multi_word_canonical(self):
        result = get_professionals_for_specialty("clinica geral")
        self.assertEqual(result, PROFESSIONALS["clinica_geral"])

        result = get_professionals_for_specialty("Clínica Geral")
        self.assertEqual(result, PROFESSIONALS["clinica_geral"])

    def test_synonym_endocrino(self):
        for term in ("Endócrino", "endocrinologista", "metabolismo", "hormonal"):
            with self.subTest(term=term):
                result = get_professionals_for_specialty(term)
                self.assertEqual(result, PROFESSIONALS["endocrinologia"])

    def test_multi_word_synonym(self):
        result = get_professionals_for_specialty("saude metabolica")
        self.assertEqual(result, PROFESSIONALS["endocrinologia"])

        result = get_professionals_for_specialty("Saúde Mental")
        self.assertEqual(result, PROFESSIONALS["psiquiatria"])

    def test_compound_string_resolves_via_substring(self):
        """Caso real da campanha de canetas: 'Endocrinologia / Saúde Metabólica'."""
        result = get_professionals_for_specialty("Endocrinologia / Saúde Metabólica")
        self.assertEqual(result, PROFESSIONALS["endocrinologia"])

    def test_saude_da_mulher_resolves_to_ginecologia(self):
        result = get_professionals_for_specialty("Ginecologia / Saúde da Mulher")
        self.assertEqual(result, PROFESSIONALS["ginecologia"])

    def test_tdah_resolves_to_psiquiatria(self):
        result = get_professionals_for_specialty("TDAH")
        self.assertEqual(result, PROFESSIONALS["psiquiatria"])

    def test_unknown_returns_empty(self):
        self.assertEqual(get_professionals_for_specialty("fisioterapia"), [])

    def test_empty_returns_empty(self):
        self.assertEqual(get_professionals_for_specialty(""), [])

    def test_multi_word_synonym_wins_over_shorter(self):
        """'clinica geral' (sinônimo multi-word) deve ter preferência sobre 'clinica' sozinho."""
        result = get_professionals_for_specialty("Clínica Geral")
        self.assertEqual(result, PROFESSIONALS["clinica_geral"])


if __name__ == "__main__":
    unittest.main()
