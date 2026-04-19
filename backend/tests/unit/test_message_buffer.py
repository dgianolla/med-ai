import importlib.util
import asyncio
import sys
import unittest
from datetime import datetime, timezone
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

models_spec = importlib.util.spec_from_file_location(
    "db.models",
    BACKEND_DIR / "db" / "models.py",
)
models_module = importlib.util.module_from_spec(models_spec)
assert models_spec and models_spec.loader
models_spec.loader.exec_module(models_module)
sys.modules["db.models"] = models_module

IncomingMessage = models_module.IncomingMessage

from services.message_buffer import (
    BufferedMessageFragment,
    MessageBufferService,
    RedisBufferBackend,
)


class InMemoryBufferBackend(RedisBufferBackend):
    def __init__(self):
        self.values: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ttl: int, only_if_missing: bool = False) -> bool:
        if only_if_missing and key in self.values:
            return False
        self.values[key] = value
        return True

    async def expire(self, key: str, ttl: int) -> None:
        return None

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)
        self.lists.pop(key, None)

    async def rpush(self, key: str, value: str) -> None:
        self.lists.setdefault(key, []).append(value)

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        items = self.lists.get(key, [])
        if stop == -1:
            return items[start:]
        return items[start: stop + 1]

    async def ltrim(self, key: str, start: int, stop: int) -> None:
        items = self.lists.get(key, [])
        if start >= len(items):
            self.lists[key] = []
            return
        if stop == -1:
            self.lists[key] = items[start:]
            return
        self.lists[key] = items[start: stop + 1]


def make_message(text: str, message_id: str) -> IncomingMessage:
    return IncomingMessage(
        wts_session_id="session-1",
        wts_message_id=message_id,
        patient_phone="5511999999999",
        patient_name="Maria",
        wts_contact_id="contact-1",
        message_type="text",
        text=text,
        file_url=None,
        received_at=datetime.now(timezone.utc),
    )


class MessageBufferServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_flushes_only_latest_token_with_consolidated_text(self) -> None:
        backend = InMemoryBufferBackend()
        dispatches: list[tuple[IncomingMessage, list[BufferedMessageFragment]]] = []

        async def dispatch_callback(
            incoming: IncomingMessage,
            fragments: list[BufferedMessageFragment],
        ) -> None:
            dispatches.append((incoming, fragments))

        service = MessageBufferService(
            backend=backend,
            debounce_seconds=0,
            buffer_ttl_seconds=60,
            dispatch_callback=dispatch_callback,
            sleep_func=lambda _: asyncio.sleep(0),
        )

        first = make_message("olá", "m1")
        second = make_message("tudo bem?", "m2")
        third = make_message("quero agendar", "m3")

        first_token = await service.buffer_message(first)
        second_token = await service.buffer_message(second)
        third_token = await service.buffer_message(third)

        self.assertFalse(await service.flush_if_latest(first, first_token))
        self.assertFalse(await service.flush_if_latest(second, second_token))
        self.assertTrue(await service.flush_if_latest(third, third_token))

        self.assertEqual(len(dispatches), 1)
        consolidated, fragments = dispatches[0]
        self.assertEqual(consolidated.text, "olá\ntudo bem?\nquero agendar")
        self.assertEqual(consolidated.wts_message_id, "m3")
        self.assertEqual([fragment.text for fragment in fragments], ["olá", "tudo bem?", "quero agendar"])

    async def test_new_message_during_dispatch_is_preserved_in_buffer(self) -> None:
        backend = InMemoryBufferBackend()
        dispatches: list[IncomingMessage] = []

        async def dispatch_callback(
            incoming: IncomingMessage,
            fragments: list[BufferedMessageFragment],
        ) -> None:
            dispatches.append(incoming)
            await service.buffer_message(make_message("mensagem nova", "m3"))

        service = MessageBufferService(
            backend=backend,
            debounce_seconds=0,
            buffer_ttl_seconds=60,
            dispatch_callback=dispatch_callback,
            sleep_func=lambda _: asyncio.sleep(0),
        )

        first = make_message("olá", "m1")
        second = make_message("tudo bem?", "m2")

        await service.buffer_message(first)
        token = await service.buffer_message(second)
        flushed = await service.flush_if_latest(second, token)

        self.assertTrue(flushed)
        self.assertEqual([incoming.text for incoming in dispatches], ["olá\ntudo bem?"])

        remaining = await backend.lrange("message-buffer:5511999999999:messages", 0, -1)
        self.assertEqual(len(remaining), 1)
        preserved = BufferedMessageFragment.model_validate_json(remaining[0])
        self.assertEqual(preserved.text, "mensagem nova")


if __name__ == "__main__":
    unittest.main()
