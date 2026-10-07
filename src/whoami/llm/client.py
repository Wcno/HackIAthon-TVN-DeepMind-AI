"""Shared LLM facade: cached, ledgered, capped and rate-limited chat and embedding calls."""

import json
import os
import random
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

from whoami.llm.cache import ResponseCache
from whoami.llm.ledger import Ledger
from whoami.llm.models import MODELS, RATE_HEADROOM, TOKEN_HEADROOM, ModelLimits
from whoami.llm.ratelimit import RateLimiter
from whoami.llm.settings import Settings

RETRYABLE_STATUS_CODES: Final = frozenset({429, 500, 503})
MAX_BACKOFF_S: Final = 60
DEFAULT_MAX_TOKENS_ESTIMATE: Final = 512
CHARS_PER_TOKEN: Final = 3  # Spanish tokenizes denser than English; overestimating is the safe side


class LLMError(RuntimeError):
    pass


class CapExceeded(LLMError):
    """Raised before any network call that would exceed the model's cap; never retried."""


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    cached: bool
    prompt_tokens: int
    completion_tokens: int
    latency_s: float

    def json(self) -> Any:
        """The first JSON value of the text; Gemma sometimes wraps it in Markdown code fences."""
        text = self.text.strip().removeprefix("```json").removeprefix("```").lstrip()
        try:
            value, _ = json.JSONDecoder().raw_decode(text)
            return value
        except ValueError as error:
            raise LLMError(f"{self.model} did not return valid JSON") from error


def _status_of(error: Exception) -> str:
    code = getattr(error, "status_code", None)
    return f"error:{code if code is not None else type(error).__name__}"


class LLM:
    def __init__(
        self,
        client: Any,
        settings: Settings,
        *,
        models: Mapping[str, ModelLimits] = MODELS,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
        max_retries: int = 6,
    ) -> None:
        self._client = client
        self._settings = settings
        self._models = models
        self._monotonic = monotonic
        self._sleep = sleep
        self._jitter = jitter
        self._max_retries = max_retries
        self._cache = ResponseCache(settings.cache_dir)
        self._ledger = Ledger(settings.ledger_path, clock)
        self._limiters: dict[str, RateLimiter] = {}

    def complete(
        self,
        model: str,
        messages: list[dict],
        *,
        purpose: str,
        evidence_ids: Iterable[str] = (),
        response_format: dict | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> Completion:
        limits = self._limits(model, "chat")
        key = self._cache.key(
            {
                "model": model,
                "messages": messages,
                "response_format": response_format,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "evidence_ids": sorted(set(evidence_ids)),
            }
        )
        started = self._monotonic()
        if (cached := self._cache.get(key)) is not None:
            latency = self._monotonic() - started
            self._ledger.record(
                model=model,
                purpose=purpose,
                cache="hit",
                status="ok",
                latency_s=latency,
                prompt_tokens=cached["prompt_tokens"],
                completion_tokens=cached["completion_tokens"],
                total_tokens=cached["prompt_tokens"] + cached["completion_tokens"],
            )
            return Completion(
                cached["text"], model, True, cached["prompt_tokens"], cached["completion_tokens"], latency
            )

        request: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if response_format is not None:
            request["response_format"] = response_format
        if max_tokens is not None:
            request["max_tokens"] = max_tokens
        estimate = (
            sum(len(str(message.get("content", ""))) for message in messages) // CHARS_PER_TOKEN
            + (max_tokens or DEFAULT_MAX_TOKENS_ESTIMATE)
        )

        def send() -> Any:
            response = self._client.chat.completions.create(**request)
            if not response.choices[0].message.content:
                raise LLMError(f"{model} returned empty content")
            return response

        response, latency = self._send_with_retries(
            limits, purpose=purpose, cost=1, tokens=estimate, n_texts=0, send=send
        )
        text = response.choices[0].message.content
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        total_tokens = getattr(usage, "total_tokens", 0) or prompt_tokens + completion_tokens
        self._limiter(limits).adjust(estimate, total_tokens)
        self._ledger.record(
            model=model,
            purpose=purpose,
            cache="miss",
            status="ok",
            latency_s=latency,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )
        self._cache.put(
            key, {"text": text, "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
        )
        return Completion(text, model, False, prompt_tokens, completion_tokens, latency)

    def embed(
        self,
        model: str,
        texts: Sequence[str],
        *,
        purpose: str,
        dimensions: int = 768,
        batch_size: int = 50,
    ) -> np.ndarray:
        limits = self._limits(model, "embedding")
        keys = [self._cache.key({"model": model, "dimensions": dimensions, "text": text}) for text in texts]
        started = self._monotonic()
        vectors: dict[str, list[float]] = {}
        for key in keys:
            if (cached := self._cache.get(key)) is not None:
                vectors[key] = cached["vector"]
        if vectors:
            hits = sum(key in vectors for key in keys)
            self._ledger.record(
                model=model,
                purpose=purpose,
                cache="hit",
                status="ok",
                latency_s=self._monotonic() - started,
                n_texts=hits,
            )

        missing = list(dict.fromkeys((key, text) for key, text in zip(keys, texts) if key not in vectors))
        for start in range(0, len(missing), batch_size):
            batch = missing[start : start + batch_size]
            batch_texts = [text for _, text in batch]

            def send(batch_texts: list[str] = batch_texts) -> Any:
                return self._client.embeddings.create(model=model, input=batch_texts, dimensions=dimensions)

            response, latency = self._send_with_retries(
                limits,
                purpose=purpose,
                cost=len(batch),
                tokens=sum(len(text) for text in batch_texts) // CHARS_PER_TOKEN,
                n_texts=len(batch),
                send=send,
            )
            self._ledger.record(
                model=model, purpose=purpose, cache="miss", status="ok", latency_s=latency, n_texts=len(batch)
            )
            for (key, _), item in zip(batch, response.data):
                vectors[key] = list(item.embedding)
                self._cache.put(key, {"vector": vectors[key]})

        if not texts:
            return np.empty((0, dimensions), dtype=np.float32)
        return np.array([vectors[key] for key in keys], dtype=np.float32)

    def spent(self, model: str) -> int:
        return self._ledger.spent(model, self._settings.budget_since)

    def remaining(self, model: str) -> int:
        return max(self._models[model].cap - self.spent(model), 0)

    def _limits(self, model: str, kind: str) -> ModelLimits:
        limits = self._models.get(model)
        if limits is None:
            raise ValueError(f"unknown model {model!r}")
        if limits.kind != kind:
            raise ValueError(f"{model} is a {limits.kind} model, not {kind}")
        return limits

    def _limiter(self, limits: ModelLimits) -> RateLimiter:
        if limits.name not in self._limiters:
            self._limiters[limits.name] = RateLimiter(
                max(int(limits.rpm * RATE_HEADROOM), 1), max(int(limits.tpm * TOKEN_HEADROOM), 1), self._monotonic, self._sleep
            )
        return self._limiters[limits.name]

    def _enforce_cap(self, limits: ModelLimits, cost: int) -> None:
        spent = self.spent(limits.name)
        if spent + cost > limits.cap:
            raise CapExceeded(f"{limits.name}: cap {limits.cap} reached ({spent} spent, {cost} requested)")

    def _send_with_retries(
        self,
        limits: ModelLimits,
        *,
        purpose: str,
        cost: int,
        tokens: int,
        n_texts: int,
        send: Callable[[], Any],
    ) -> tuple[Any, float]:
        for attempt in range(self._max_retries + 1):
            self._enforce_cap(limits, cost)
            self._limiter(limits).acquire(tokens)
            started = self._monotonic()
            try:
                response = send()
            except Exception as error:
                self._ledger.record(
                    model=limits.name,
                    purpose=purpose,
                    cache="miss",
                    status=_status_of(error),
                    latency_s=self._monotonic() - started,
                    n_texts=n_texts,
                )
                retryable = getattr(error, "status_code", None) in RETRYABLE_STATUS_CODES
                if not retryable or attempt == self._max_retries:
                    if isinstance(error, LLMError):
                        raise
                    raise LLMError(f"{limits.name} call failed: {error}") from error
                self._sleep(min(MAX_BACKOFF_S, 2**attempt) + self._jitter())
                continue
            return response, self._monotonic() - started
        raise AssertionError("unreachable")  # pragma: no cover


def default_llm() -> LLM:
    settings = Settings.from_env()
    load_dotenv(settings.env_file)
    client = OpenAI(api_key=os.environ["GEMINI_API_KEY"], base_url=settings.base_url, max_retries=0)
    return LLM(client, settings)
