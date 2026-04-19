import asyncio
import logging
import urllib.parse
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import httpx
from pydantic import BaseModel

from config import get_settings
from db.models import IncomingMessage, MessageType

logger = logging.getLogger(__name__)


class BufferedMessageFragment(BaseModel):
    wts_message_id: str
    message_type: MessageType
    text: str
    file_url: str | None = None
    received_at: datetime


class RedisBufferBackend:
    async def get(self, key: str) -> Optional[str]:
        raise NotImplementedError

    async def set(self, key: str, value: str, ttl: int, only_if_missing: bool = False) -> bool:
        raise NotImplementedError

    async def expire(self, key: str, ttl: int) -> None:
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        raise NotImplementedError

    async def rpush(self, key: str, value: str) -> None:
        raise NotImplementedError

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        raise NotImplementedError

    async def ltrim(self, key: str, start: int, stop: int) -> None:
        raise NotImplementedError


class UpstashRestBufferBackend(RedisBufferBackend):
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def _request(self, path: str) -> dict:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"{self.base_url}/{path}",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    async def get(self, key: str) -> Optional[str]:
        data = await self._request(f"get/{urllib.parse.quote(key, safe='')}")
        return data.get("result")

    async def set(self, key: str, value: str, ttl: int, only_if_missing: bool = False) -> bool:
        path = (
            f"set/{urllib.parse.quote(key, safe='')}/{urllib.parse.quote(value, safe='')}"
            f"/nx/ex/{ttl}"
            if only_if_missing
            else f"set/{urllib.parse.quote(key, safe='')}/{urllib.parse.quote(value, safe='')}/ex/{ttl}"
        )
        data = await self._request(path)
        if only_if_missing:
            return data.get("result") == "OK"
        return True

    async def expire(self, key: str, ttl: int) -> None:
        await self._request(f"expire/{urllib.parse.quote(key, safe='')}/{ttl}")

    async def delete(self, key: str) -> None:
        await self._request(f"del/{urllib.parse.quote(key, safe='')}")

    async def rpush(self, key: str, value: str) -> None:
        await self._request(
            f"rpush/{urllib.parse.quote(key, safe='')}/{urllib.parse.quote(value, safe='')}"
        )

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        data = await self._request(f"lrange/{urllib.parse.quote(key, safe='')}/{start}/{stop}")
        result = data.get("result") or []
        return result if isinstance(result, list) else []

    async def ltrim(self, key: str, start: int, stop: int) -> None:
        await self._request(f"ltrim/{urllib.parse.quote(key, safe='')}/{start}/{stop}")


class MessageBufferService:
    def __init__(
        self,
        backend: RedisBufferBackend,
        debounce_seconds: int,
        buffer_ttl_seconds: int,
        dispatch_callback: Callable[[IncomingMessage, list[BufferedMessageFragment]], Awaitable[None]],
        sleep_func: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.backend = backend
        self.debounce_seconds = debounce_seconds
        self.buffer_ttl_seconds = buffer_ttl_seconds
        self.dispatch_callback = dispatch_callback
        self.sleep_func = sleep_func
        self._tasks: set[asyncio.Task] = set()

    def _conversation_key(self, incoming: IncomingMessage) -> str:
        return incoming.patient_phone

    def _buffer_key(self, conversation_key: str) -> str:
        return f"message-buffer:{conversation_key}:messages"

    def _token_key(self, conversation_key: str) -> str:
        return f"message-buffer:{conversation_key}:token"

    def _lock_key(self, conversation_key: str, token: str) -> str:
        return f"message-buffer:{conversation_key}:lock:{token}"

    def _track_task(self, task: asyncio.Task) -> None:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def buffer_and_schedule(self, incoming: IncomingMessage) -> str:
        token = await self.buffer_message(incoming)
        task = asyncio.create_task(self.flush_if_latest(incoming, token))
        self._track_task(task)
        return token

    async def buffer_message(self, incoming: IncomingMessage) -> str:
        conversation_key = self._conversation_key(incoming)
        fragment = BufferedMessageFragment(
            wts_message_id=incoming.wts_message_id,
            message_type=incoming.message_type,
            text=incoming.text,
            file_url=incoming.file_url,
            received_at=incoming.received_at,
        )

        await self.backend.rpush(
            self._buffer_key(conversation_key),
            fragment.model_dump_json(),
        )

        token = uuid4().hex
        await self.backend.set(
            self._token_key(conversation_key),
            token,
            ttl=self.buffer_ttl_seconds,
        )
        await self.backend.expire(self._buffer_key(conversation_key), self.buffer_ttl_seconds)

        logger.info(
            "[MESSAGE_BUFFER] Fragmento armazenado | conversation=%s | type=%s | token=%s | text=%s",
            conversation_key,
            incoming.message_type,
            token,
            " ".join(incoming.text.split())[:120],
        )
        return token

    async def flush_if_latest(self, incoming: IncomingMessage, token: str) -> bool:
        await self.sleep_func(self.debounce_seconds)

        conversation_key = self._conversation_key(incoming)
        current_token = await self.backend.get(self._token_key(conversation_key))
        if current_token != token:
            logger.info(
                "[MESSAGE_BUFFER] Flush cancelado | conversation=%s | scheduled=%s | current=%s",
                conversation_key,
                token,
                current_token,
            )
            return False

        acquired = await self.backend.set(
            self._lock_key(conversation_key, token),
            str(datetime.now(timezone.utc).timestamp()),
            ttl=max(self.debounce_seconds * 2, 30),
            only_if_missing=True,
        )
        if not acquired:
            logger.info(
                "[MESSAGE_BUFFER] Flush já em andamento | conversation=%s | token=%s",
                conversation_key,
                token,
            )
            return False

        try:
            current_token = await self.backend.get(self._token_key(conversation_key))
            if current_token != token:
                logger.info(
                    "[MESSAGE_BUFFER] Flush invalidado após lock | conversation=%s | scheduled=%s | current=%s",
                    conversation_key,
                    token,
                    current_token,
                )
                return False

            raw_fragments = await self.backend.lrange(self._buffer_key(conversation_key), 0, -1)
            fragments = [BufferedMessageFragment.model_validate_json(item) for item in raw_fragments]
            if not fragments:
                logger.warning(
                    "[MESSAGE_BUFFER] Flush sem fragmentos | conversation=%s | token=%s",
                    conversation_key,
                    token,
                )
                return False

            consolidated_text = "\n".join(
                fragment.text.strip()
                for fragment in fragments
                if fragment.text and fragment.text.strip()
            ).strip()
            last_fragment = fragments[-1]
            consolidated = incoming.model_copy(
                update={
                    "wts_message_id": last_fragment.wts_message_id,
                    "message_type": last_fragment.message_type,
                    "text": consolidated_text or last_fragment.text,
                    "file_url": last_fragment.file_url,
                    "received_at": last_fragment.received_at,
                }
            )

            logger.info(
                "[MESSAGE_BUFFER] Flush liberado | conversation=%s | token=%s | fragments=%s | text=%s",
                conversation_key,
                token,
                len(fragments),
                " ".join(consolidated.text.split())[:120],
            )
            await self.dispatch_callback(consolidated, fragments)

            await self.backend.ltrim(self._buffer_key(conversation_key), len(fragments), -1)
            await self.backend.expire(self._buffer_key(conversation_key), self.buffer_ttl_seconds)
            return True
        finally:
            await self.backend.delete(self._lock_key(conversation_key, token))


_message_buffer_service: MessageBufferService | None = None


def get_message_buffer_service() -> MessageBufferService:
    global _message_buffer_service
    if _message_buffer_service is None:
        settings = get_settings()
        if not settings.upstash_redis_rest_url or not settings.upstash_redis_rest_token:
            raise RuntimeError("Upstash Redis REST não configurado para o buffer de mensagens.")

        async def _dispatch_callback(
            incoming: IncomingMessage,
            fragments: list[BufferedMessageFragment],
        ) -> None:
            from orchestrator.orchestrator import dispatch

            await dispatch(incoming, buffered_fragments=fragments)

        backend = UpstashRestBufferBackend(
            base_url=settings.upstash_redis_rest_url,
            token=settings.upstash_redis_rest_token,
        )
        _message_buffer_service = MessageBufferService(
            backend=backend,
            debounce_seconds=settings.message_buffer_seconds,
            buffer_ttl_seconds=settings.message_buffer_ttl_seconds,
            dispatch_callback=_dispatch_callback,
        )
    return _message_buffer_service
