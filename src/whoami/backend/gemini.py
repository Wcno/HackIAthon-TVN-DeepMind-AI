"""Bounded JSON generation, with a persistent cache shared with the G4 lane."""

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from openai import APIConnectionError, APIStatusError, AsyncOpenAI

from whoami.backend.repository import EditorialRepository, content_hash
from whoami.backend.settings import Settings


class GenerationUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class GenerationResult:
    content: dict
    cached: bool
    attempts: int


class GeminiClient:
    def __init__(self, repository: EditorialRepository, settings: Settings, *, transport=None):
        self.repository = repository
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.gemini_api_key or "offline-unconfigured",
            base_url=settings.gemini_base_url,
            max_retries=0,
            timeout=settings.generation_timeout,
            http_client=httpx.AsyncClient(transport=transport),
        )
        self.lock = asyncio.Lock()

    async def close(self) -> None:
        await self.client.close()

    async def generate(self, messages: list[dict[str, str]], evidence: Mapping[str, dict], *,
                       validate: Callable[[dict], None], prompt_version: str = "1", temperature: float = 0.0) -> GenerationResult:
        request = {"model": self.settings.gemini_model, "messages": messages, "temperature": temperature,
                   "response_format": {"type": "json_object"}}
        key = content_hash({"request": request, "base_url": self.settings.gemini_base_url,
                            "prompt_version": prompt_version, "evidence": dict(evidence)})
        try:
            async with asyncio.timeout(self.settings.generation_timeout):
                async with self.lock:
                    try:
                        cached = self.repository.cache_get(key)
                        if cached is not None:
                            if not isinstance(cached, dict):
                                raise ValueError("Expected cached JSON object")
                            validate(cached)
                            return GenerationResult(cached, True, 0)
                    except (ValueError, TypeError, AttributeError):
                        self.repository.cache_delete(key)
                        if self.settings.offline:
                            raise GenerationUnavailable("The cached response is invalid; online regeneration is required.") from None
                    if self.settings.offline:
                        raise GenerationUnavailable("Offline mode permits cached generation only.")
                    if not self.settings.gemini_api_key:
                        raise GenerationUnavailable("The generation provider is not configured.")
                    return await self._request(request, key, validate)
        except TimeoutError:
            raise GenerationUnavailable("The generation deadline was exceeded.") from None

    async def _request(self, request: dict, key: str, validate: Callable[[dict], None]) -> GenerationResult:
        for attempt in range(1, self.settings.generation_attempts + 1):
            try:
                response = await self.client.chat.completions.create(**request)
            except APIConnectionError:
                raise GenerationUnavailable("The generation provider could not be reached.") from None
            except APIStatusError as error:
                if error.status_code in (429, 503) and attempt < self.settings.generation_attempts:
                    await asyncio.sleep(self._retry_delay(error.response, attempt))
                    continue
                raise GenerationUnavailable(f"The generation provider returned HTTP {error.status_code}.") from None
            try:
                content = json.loads(response.choices[0].message.content)
                if not isinstance(content, dict):
                    raise ValueError("Expected a JSON object")
                validate(content)
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                raise GenerationUnavailable("The provider returned an invalid structured response.") from None
            self.repository.cache_put(key, content)
            return GenerationResult(content, False, attempt)
        raise GenerationUnavailable("The generation retry budget was exhausted.")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        value = response.headers.get("Retry-After")
        if value is not None:
            try:
                delay = float(value)
            except ValueError:
                try:
                    delay = (parsedate_to_datetime(value).astimezone(UTC) - datetime.now(UTC)).total_seconds()
                except (ValueError, TypeError, OverflowError):
                    delay = float(2 ** (attempt - 1))
            if delay >= 0 and delay < float("inf"):
                return delay
        return float(2 ** (attempt - 1))
