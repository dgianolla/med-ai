import sys
import unittest
from pathlib import Path
from types import ModuleType
import importlib.util

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

anthropic_stub = ModuleType("anthropic")
anthropic_stub.AsyncAnthropic = object
sys.modules.setdefault("anthropic", anthropic_stub)

pydantic_stub = ModuleType("pydantic")


class BaseModel:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


pydantic_stub.BaseModel = BaseModel
sys.modules.setdefault("pydantic", pydantic_stub)

config_stub = ModuleType("config")
config_stub.get_settings = lambda: object()
sys.modules.setdefault("config", config_stub)

db_package = ModuleType("db")
db_package.__path__ = [str(BACKEND_DIR / "db")]
sys.modules.setdefault("db", db_package)

models_spec = importlib.util.spec_from_file_location(
    "db.models",
    BACKEND_DIR / "db" / "models.py",
)
models_module = importlib.util.module_from_spec(models_spec)
assert models_spec and models_spec.loader
models_spec.loader.exec_module(models_module)
sys.modules["db.models"] = models_module

from agents.exam_quote_utils import has_exam_order, has_exam_quote_handoff_context, wants_exam_quote
from db.models import HandoffPayload, SessionContext


class ExamQuoteRoutingTest(unittest.TestCase):
    def _ctx(self, *, exam_content=None, handoff_payload=None) -> SessionContext:
        from datetime import datetime, timezone

        return SessionContext(
            session_id="s1",
            patient_phone="5511999999999",
            wts_session_id="w1",
            current_agent="exams",
            conversation_history=[],
            handoff_payload=handoff_payload,
            patient_metadata={"name": "Maria"},
            exam_content=exam_content,
            created_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc),
        )

    def test_detects_exam_quote_intent(self) -> None:
        self.assertTrue(wants_exam_quote("Queria ver quanto fica esse exame"))
        self.assertTrue(wants_exam_quote("Pode me passar o orçamento?"))
        self.assertFalse(wants_exam_quote("Quero marcar consulta"))

    def test_detects_exam_order_from_attachment(self) -> None:
        ctx = self._ctx(exam_content="https://arquivo/pedido.png")
        self.assertTrue(has_exam_order(ctx, "segue"))

    def test_detects_exam_order_from_text(self) -> None:
        ctx = self._ctx()
        self.assertTrue(has_exam_order(ctx, "tenho o pedido médico aqui"))
        self.assertTrue(has_exam_order(ctx, "estou com a guia e quero orçamento"))

    def test_detects_handoff_context_for_exam_quote(self) -> None:
        payload = HandoffPayload(
            type="to_commercial",
            reason="Paciente necessita fazer orçamento de exames.",
            context={"human_handoff_type": "exam_quote"},
        )
        ctx = self._ctx(handoff_payload=payload)
        self.assertTrue(has_exam_quote_handoff_context(ctx))


if __name__ == "__main__":
    unittest.main()
