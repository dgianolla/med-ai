import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

fastapi_stub = ModuleType("fastapi")


class APIRouter:
    def post(self, *_args, **_kwargs):
        def decorator(func):
            return func
        return decorator

    def get(self, *_args, **_kwargs):
        def decorator(func):
            return func
        return decorator


class BackgroundTasks:
    def add_task(self, *_args, **_kwargs):
        return None


class HTTPException(Exception):
    pass


class Request:
    pass


fastapi_stub.APIRouter = APIRouter
fastapi_stub.BackgroundTasks = BackgroundTasks
fastapi_stub.HTTPException = HTTPException
fastapi_stub.Request = Request
sys.modules.setdefault("fastapi", fastapi_stub)

config_stub = ModuleType("config")
config_stub.get_settings = lambda: SimpleNamespace(wts_confirmation_channel_id="channel-1")
sys.modules.setdefault("config", config_stub)

integrations_stub = ModuleType("integrations.whatsapp")
integrations_stub.parse_webhook = lambda body: body
integrations_stub.get_whatsapp_client = lambda: None
sys.modules["integrations.whatsapp"] = integrations_stub

webhook_spec = importlib.util.spec_from_file_location(
    "confirmation_webhook_module",
    BACKEND_DIR / "routes" / "confirmation_webhook.py",
)
webhook_module = importlib.util.module_from_spec(webhook_spec)
assert webhook_spec and webhook_spec.loader
webhook_spec.loader.exec_module(webhook_module)


class ConfirmationWebhookReplyTest(unittest.IsolatedAsyncioTestCase):
    async def test_reply_uses_outbound_when_session_is_absent(self) -> None:
        fake_client = SimpleNamespace(
            send_text=AsyncMock(),
            send_outbound_text=AsyncMock(return_value="msg-1"),
        )
        webhook_module.get_settings = lambda: SimpleNamespace(wts_confirmation_channel_id="channel-1")

        integrations_stub.get_whatsapp_client = lambda: fake_client

        incoming = SimpleNamespace(
            wts_session_id="",
            wts_message_id="wamid.reply",
            patient_phone="5515997615435",
        )

        await webhook_module._reply_to_confirmation_message(incoming, "Consulta confirmada.")

        fake_client.send_text.assert_not_called()
        fake_client.send_outbound_text.assert_awaited_once_with(
            to_phone="5515997615435",
            text="Consulta confirmada.",
            from_channel_id="channel-1",
        )


if __name__ == "__main__":
    unittest.main()
