"""Grounded structured generation against a preloaded, loopback-only QVAC engine.

No cloud key, quota ledger, registry, download or alternative provider is used.
The editorial validators remain authoritative over the model's JSON grammar.
"""

import asyncio
import json
import sqlite3
from collections.abc import Callable, Mapping

import httpx

from whoami.backend.gemini import GenerationResult, GenerationUnavailable, InvalidGeneration
from whoami.backend.repository import EditorialRepository, content_hash
from whoami.backend.settings import Settings

GENERATOR_SHA256 = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"


class QvacClient:
    def __init__(self, repository: EditorialRepository, settings: Settings, *, transport=None):
        self.repository, self.settings = repository, settings
        self.client = httpx.AsyncClient(base_url=settings.qvac_base_url, transport=transport,
                                       trust_env=False, follow_redirects=False,
                                       timeout=settings.generation_timeout)
        self.lock = asyncio.Lock()

    async def close(self) -> None:
        await self.client.aclose()

    async def generate(self, messages: list[dict[str, str]], evidence: Mapping[str, dict], *,
                       validate: Callable[[dict], dict | None], prompt_version: str = "1", temperature: float = 0.0,
                       response_format: dict | None = None, max_tokens: int = 1000) -> GenerationResult:
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
            raise GenerationUnavailable("Generation requires a positive token limit.")
        request = {"model": self.settings.generation_model, "messages": messages, "temperature": temperature,
                   "max_tokens": max_tokens, "reasoning_budget": False,
                   "response_format": response_format or {"type": "json_object"}}
        key = content_hash({"request": request, "provider": "qvac-0.21.0", "model_sha256": GENERATOR_SHA256,
                            "base_url": self.settings.qvac_base_url, "prompt_version": prompt_version,
                            "evidence": dict(evidence)})
        try:
            async with asyncio.timeout(self.settings.generation_timeout):
                async with self.lock:
                    cached = self.repository.cache_get(key)
                    if cached is not None:
                        try:
                            if not isinstance(cached, dict):
                                raise ValueError("Expected a JSON object")
                            return GenerationResult(validate(cached) or cached, True, 0)
                        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                            self.repository.cache_delete(key)
                    response = await self.client.post("chat/completions", json=request)
                    if response.status_code != 200:
                        raise GenerationUnavailable(f"QVAC returned HTTP {response.status_code}; no cloud fallback was attempted.")
                    content = None
                    try:
                        choice = response.json()["choices"][0]
                        if choice.get("finish_reason") != "stop":
                            raise ValueError("Incomplete generation")
                        content = json.loads(choice["message"]["content"])
                        if not isinstance(content, dict):
                            raise ValueError("Expected a JSON object")
                        content = validate(content) or content
                    except Exception as error:
                        raise InvalidGeneration(content if isinstance(content, dict) else None, error) from None
                    self.repository.cache_put(key, content)
                    return GenerationResult(content, False, 1)
        except (TimeoutError, httpx.TimeoutException):
            raise GenerationUnavailable("The local generation deadline was exceeded.") from None
        except httpx.HTTPError:
            raise GenerationUnavailable("QVAC is unavailable. Start the prepared local engine or use precalculated answers.") from None
        except (OSError, RuntimeError, sqlite3.Error):
            raise GenerationUnavailable("Local generation bookkeeping is unavailable.") from None
