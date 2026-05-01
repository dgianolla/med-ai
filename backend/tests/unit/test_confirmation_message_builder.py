import importlib.util
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

builder_spec = importlib.util.spec_from_file_location(
    "confirmation_message_builder_module",
    BACKEND_DIR / "services" / "confirmation_message_builder.py",
)
builder_module = importlib.util.module_from_spec(builder_spec)
assert builder_spec and builder_spec.loader
sys.modules["confirmation_message_builder_module"] = builder_module
builder_spec.loader.exec_module(builder_module)


class ConfirmationMessageBuilderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.schedule = {
            "id": "appointment-1",
            "nome": "Maria",
            "data": "2026-05-02",
            "horaInicio": "14:30:00",
            "profissionalSaude": {"nome": "Dr. Ricardo"},
            "telefonePrincipal": "5511999999999",
        }

    def test_build_confirmation_message_is_deterministic(self) -> None:
        first = builder_module.build_confirmation_message(self.schedule)
        second = builder_module.build_confirmation_message(self.schedule)

        self.assertEqual(first.template_key, second.template_key)
        self.assertEqual(first.text, second.text)

    def test_build_confirmation_message_keeps_required_keywords(self) -> None:
        message = builder_module.build_confirmation_message(self.schedule)

        self.assertIn("SIM", message.text)
        self.assertIn("NÃO", message.text)
        self.assertIn("REMARCAR", message.text)
        self.assertIn("Maria", message.text)
        self.assertIn("Dr. Ricardo", message.text)
        self.assertIn("02/05/2026", message.text)
        self.assertIn("14:30", message.text)
        self.assertTrue(message.template_key.startswith("v1_"))
        self.assertEqual(message.template_version, "2026-05-01")


if __name__ == "__main__":
    unittest.main()
