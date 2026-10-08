"""Bounded JSON generation, with a persistent cache shared with the G4 lane."""

import asyncio
import json
import os
import sqlite3
import time
from pathlib import Path
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from openai import APIConnectionError, APIStatusError, AsyncOpenAI

from whoami.backend.repository import EditorialRepository, content_hash
from whoami.backend.settings import Settings
from whoami.backend.quota import GenerationQuota, QuotaUnavailable


_INVALID_RESPONSE_ERRORS = (ValueError, KeyError, IndexError, TypeError, AttributeError)


class GenerationUnavailable(ValueError):
    pass


class InvalidGeneration(GenerationUnavailable):
    """The provider answered but `validate` rejected the reply; `content` is that reply (None if it was not JSON)."""

    def __init__(self, content: dict | None, cause: Exception):
        super().__init__("The provider returned an invalid structured response.")
        self.content = content
        self.cause = cause


@dataclass(frozen=True)
class GenerationResult:
    content: dict
    cached: bool
    attempts: int


class GeminiClient:
    def __init__(self, repository: EditorialRepository, settings: Settings, *, transport=None,
                 quota_limits=None, quota_database=None, ledger_path=None, budget_since=None):
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
        # Injected HTTP transports always isolate bookkeeping beside the test database.
        default_ledger = (settings.database.with_suffix(".ledger.jsonl") if transport is not None
                          else Path(os.environ.get("WHOAMI_LEDGER", Path.home() / ".cache/whoami/ledger.jsonl")))
        ledger_path = Path(ledger_path or default_ledger)
        self.quota = GenerationQuota(settings.gemini_model, ledger_path=ledger_path,
                                     database=Path(quota_database or (ledger_path.with_suffix(".quota.sqlite3") if transport is not None else os.environ.get("WHOAMI_GENERATION_QUOTA_DB", ledger_path.with_suffix(".quota.sqlite3")))),
                                     limits=quota_limits, budget_since=budget_since,
                                     daily_request_limit=settings.generation_daily_limit)

    async def close(self) -> None:
        await self.client.close()

    async def generate(self, messages: list[dict[str, str]], evidence: Mapping[str, dict], *,
                       validate: Callable[[dict], dict | None], prompt_version: str = "1", temperature: float = 0.0,
                       response_format: dict | None = None, max_tokens: int = 1000) -> GenerationResult:
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
            raise GenerationUnavailable("Generation requires a positive token limit.")
        request = {"model": self.settings.gemini_model, "messages": messages, "temperature": temperature,
                   "response_format": response_format if response_format is not None else {"type": "json_object"},
                   "max_tokens": max_tokens}
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
                            return GenerationResult(validate(cached) or cached, True, 0)
                    except _INVALID_RESPONSE_ERRORS:
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
        except QuotaUnavailable as error:
            raise GenerationUnavailable(str(error)) from None
        except (OSError, RuntimeError, sqlite3.Error, ValueError) as error:
            if isinstance(error, GenerationUnavailable):
                raise
            raise GenerationUnavailable("Generation bookkeeping or provider processing is unavailable.") from None

    async def _request(self, request: dict, key: str, validate: Callable[[dict], dict | None]) -> GenerationResult:
        estimate = (len(json.dumps(request, ensure_ascii=False)) + 2) // 3 + request["max_tokens"]
        for attempt in range(1, self.settings.generation_attempts + 1):
            identifier = await asyncio.to_thread(self.quota.reserve, estimate)
            started = time.monotonic()
            try:
                response = await self.client.chat.completions.create(**request)
            except asyncio.CancelledError:
                await asyncio.to_thread(self.quota.finish, identifier, status="error:cancelled", latency=time.monotonic() - started)
                raise
            except APIConnectionError:
                await asyncio.to_thread(self.quota.finish, identifier, status="error:connection", latency=time.monotonic() - started)
                raise GenerationUnavailable("The generation provider could not be reached.") from None
            except APIStatusError as error:
                await asyncio.to_thread(self.quota.finish, identifier, status=f"error:{error.status_code}", latency=time.monotonic() - started)
                if error.status_code in (429, 503) and attempt < self.settings.generation_attempts:
                    await asyncio.sleep(self._retry_delay(error.response, attempt))
                    continue
                raise GenerationUnavailable(f"The generation provider returned HTTP {error.status_code}.") from None
            except Exception:
                await asyncio.to_thread(self.quota.finish, identifier, status="error:provider", latency=time.monotonic() - started)
                raise GenerationUnavailable("The generation provider response could not be processed.") from None
            usage = getattr(response, "usage", None)
            prompt = getattr(usage, "prompt_tokens", 0) or 0
            completion = getattr(usage, "completion_tokens", 0) or 0
            total = (getattr(usage, "total_tokens", None) or prompt + completion) if usage is not None else None
            content = None
            try:
                content = json.loads(response.choices[0].message.content)
                if not isinstance(content, dict):
                    raise ValueError("Expected a JSON object")
                content = validate(content) or content
            except Exception as error:
                await asyncio.to_thread(self.quota.finish, identifier, status="error:invalid_response", latency=time.monotonic() - started,
                                        prompt_tokens=prompt, completion_tokens=completion, total_tokens=total)
                raise InvalidGeneration(content if isinstance(content, dict) else None, error) from None
            await asyncio.to_thread(self.quota.finish, identifier, status="ok", latency=time.monotonic() - started,
                                    prompt_tokens=prompt, completion_tokens=completion, total_tokens=total)
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
