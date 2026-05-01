import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

pydantic_stub = ModuleType("pydantic")


class BaseModel:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


pydantic_stub.BaseModel = BaseModel
sys.modules.setdefault("pydantic", pydantic_stub)

anthropic_stub = ModuleType("anthropic")
anthropic_stub.AsyncAnthropic = object
sys.modules.setdefault("anthropic", anthropic_stub)

postgrest_module = ModuleType("postgrest")
postgrest_exceptions = ModuleType("postgrest.exceptions")


class APIError(Exception):
    def __init__(self, message: str = ""):
        super().__init__(message)
        self.message = message


postgrest_exceptions.APIError = APIError
sys.modules.setdefault("postgrest", postgrest_module)
sys.modules.setdefault("postgrest.exceptions", postgrest_exceptions)

config_stub = ModuleType("config")
config_stub.get_settings = lambda: SimpleNamespace(anthropic_api_key="test-key")
sys.modules.setdefault("config", config_stub)

db_package = ModuleType("db")
db_package.__path__ = [str(BACKEND_DIR / "db")]
sys.modules.setdefault("db", db_package)

db_client_stub = ModuleType("db.client")
db_client_stub.get_supabase = AsyncMock()
sys.modules.setdefault("db.client", db_client_stub)

models_spec = importlib.util.spec_from_file_location(
    "db.models",
    BACKEND_DIR / "db" / "models.py",
)
models_module = importlib.util.module_from_spec(models_spec)
assert models_spec and models_spec.loader
models_spec.loader.exec_module(models_module)
sys.modules["db.models"] = models_module

integrations_package = ModuleType("integrations")
integrations_package.__path__ = [str(BACKEND_DIR / "integrations")]
sys.modules.setdefault("integrations", integrations_package)

helena_client_stub = ModuleType("integrations.helena_client")
helena_client_stub.complete_session = AsyncMock()
sys.modules.setdefault("integrations.helena_client", helena_client_stub)

scheduling_api_stub = ModuleType("integrations.scheduling_api")
scheduling_api_stub.cancel_appointment = AsyncMock()
scheduling_api_stub.confirm_appointment = AsyncMock()
sys.modules.setdefault("integrations.scheduling_api", scheduling_api_stub)

confirmation_spec = importlib.util.spec_from_file_location(
    "confirmation_agent_module",
    BACKEND_DIR / "agents" / "confirmation_agent.py",
)
confirmation_module = importlib.util.module_from_spec(confirmation_spec)
assert confirmation_spec and confirmation_spec.loader
confirmation_spec.loader.exec_module(confirmation_module)

IncomingMessage = models_module.IncomingMessage


def make_message(text: str) -> IncomingMessage:
    return IncomingMessage(
        wts_session_id="helena-session-1",
        wts_message_id="msg-1",
        patient_phone="5511999999999",
        patient_name="Maria",
        wts_contact_id="contact-1",
        message_type="text",
        text=text,
        file_url=None,
        received_at=datetime.now(timezone.utc),
    )


class ConfirmationAgentTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.active = {
            "id": "confirmation-1",
            "appointment_id": "appointment-1",
            "patient_name": "Maria",
            "patient_phone": "5511999999999",
            "status": "sent",
            "helena_session_id": None,
        }
        confirmation_module._find_active_confirmation = AsyncMock(return_value=dict(self.active))
        confirmation_module._update_confirmation = AsyncMock()
        confirmation_module.complete_session = AsyncMock(return_value={"id": "helena-session-1"})
        confirmation_module.confirm_appointment = AsyncMock(return_value={"ok": True})
        confirmation_module.cancel_appointment = AsyncMock(return_value={"ok": True})

    async def test_alterar_persists_session_and_completes_helena(self) -> None:
        confirmation_module._classify_confirmation_response = AsyncMock(
            return_value={"intent": "alterar", "reply": "Vamos ajustar pelo WhatsApp da clínica."}
        )

        result = await confirmation_module.handle_confirmation(make_message("ALTERAR"))

        self.assertEqual(result["intent"], "alterar")
        self.assertEqual(result["status"], "sent")
        self.assertTrue(result["is_final"])
        confirmation_module._update_confirmation.assert_any_await(
            {"helena_session_id": "helena-session-1"},
            "confirmation-1",
        )
        confirmation_module.complete_session.assert_awaited_once_with(
            "helena-session-1",
            reactivate_on_new_message=False,
            stop_bot_in_execution=True,
        )
        confirmation_module.confirm_appointment.assert_not_awaited()
        confirmation_module.cancel_appointment.assert_not_awaited()

    def test_normalize_confirmation_intent_maps_remarcar_to_alterar(self) -> None:
        self.assertEqual(confirmation_module._normalize_confirmation_intent("remarcar"), "alterar")

    def test_fallback_classify_accepts_remarcar(self) -> None:
        self.assertEqual(confirmation_module._fallback_classify("Quero remarcar"), "remarcar")

    async def test_sim_confirms_appointment_and_completes_helena(self) -> None:
        confirmation_module._classify_confirmation_response = AsyncMock(
            return_value={"intent": "sim", "reply": "Consulta confirmada."}
        )

        result = await confirmation_module.handle_confirmation(make_message("SIM"))

        self.assertEqual(result["intent"], "sim")
        self.assertEqual(result["status"], "confirmed")
        self.assertTrue(result["is_final"])
        confirmation_module.confirm_appointment.assert_awaited_once_with("appointment-1")
        confirmation_module._update_confirmation.assert_any_await(
            {"status": "confirmed"},
            "confirmation-1",
        )
        confirmation_module.complete_session.assert_awaited_once_with(
            "helena-session-1",
            reactivate_on_new_message=False,
            stop_bot_in_execution=True,
        )


if __name__ == "__main__":
    unittest.main()
