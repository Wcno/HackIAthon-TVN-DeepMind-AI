"""The batch generators' `LLM.complete`, answered by the app's own Gemini client, quota and cache."""

import asyncio
import json
from collections.abc import Callable, Iterable, Mapping

from whoami.backend.gemini import GeminiClient, GenerationUnavailable
from whoami.llm.client import Completion

Validator = Callable[[dict], object]


class CompletionUnavailable(Exception):
    """Gemini could not answer (connection, quota, offline mode or an unusable reply): trying again is safe.

    Deliberately not an `LLMError` nor a `ValueError`, which the generators read as "the sources do not answer"."""


class GeminiCompletions:
    """Runs the app's async Gemini client from a worker thread, as the synchronous generators expect.

    `validators` maps a call's purpose to the check its reply must pass to be cached; other purposes accept any JSON."""

    def __init__(self, gemini: GeminiClient, loop: asyncio.AbstractEventLoop, *, prompt_version: str,
                 validators: Mapping[str, Validator] | None = None) -> None:
        self._gemini = gemini
        self._loop = loop
        self._prompt_version = prompt_version
        self._validators = validators or {}

    def complete(self, model: str, messages: list[dict], *, purpose: str, evidence_ids: Iterable[str] = (),
                 response_format: dict | None = None, temperature: float = 0.0, max_tokens: int | None = None) -> Completion:
        validator = self._validators.get(purpose)
        request = self._gemini.generate(messages, {}, validate=lambda data: validator(data) if validator else None,
                                        prompt_version=self._prompt_version, temperature=temperature,
                                        response_format=response_format, max_tokens=max_tokens or 1000)
        try:
            result = asyncio.run_coroutine_threadsafe(request, self._loop).result()
        except GenerationUnavailable as error:
            raise CompletionUnavailable(str(error)) from error
        return Completion(json.dumps(result.content, ensure_ascii=False), model, result.cached, 0, 0, 0.0)
