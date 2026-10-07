import json
from dataclasses import replace
from types import SimpleNamespace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from whoami.llm import default_llm
from whoami.llm.client import LLM, CapExceeded, Completion, InvalidJSON, LLMError
from whoami.llm.cache import ResponseCache
from whoami.llm.ledger import Ledger, format_summary
from whoami.llm.models import MODELS, ModelLimits, RATE_HEADROOM
from whoami.llm.ratelimit import RateLimiter
from whoami.llm.settings import Settings, find_env_file, quota_day_start


def test_models_registry_holds_only_the_allowed_models():
    assert set(MODELS) == {
        "gemma-4-26b-a4b-it",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-embedding-2",
    }
    assert MODELS["gemini-embedding-2"].kind == "embedding"
    assert isinstance(MODELS["gemma-4-26b-a4b-it"], ModelLimits)


def test_quota_day_start_is_the_latest_los_angeles_midnight():
    now = datetime(2026, 10, 7, 6, 30, tzinfo=UTC)
    assert quota_day_start(now) == datetime(2026, 10, 6, 7, 0, tzinfo=UTC)


def test_quota_day_start_after_los_angeles_midnight():
    now = datetime(2026, 10, 7, 8, 0, tzinfo=UTC)
    assert quota_day_start(now) == datetime(2026, 10, 7, 7, 0, tzinfo=UTC)


def test_find_env_file_prefers_the_root_env(tmp_path: Path):
    (tmp_path / ".env").write_text("")
    assert find_env_file(tmp_path) == tmp_path / ".env"


def test_find_env_file_follows_a_worktree_to_the_main_checkout(tmp_path: Path):
    main = tmp_path / "main"
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {main}/.git/worktrees/wt\n")
    assert find_env_file(worktree) == main / ".env"


def test_find_env_file_defaults_to_the_root_env(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    assert find_env_file(tmp_path) == tmp_path / ".env"


def test_settings_from_env_reads_overrides(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("WHOAMI_ENV_FILE", str(tmp_path / "e"))
    monkeypatch.setenv("WHOAMI_LLM_CACHE", str(tmp_path / "c"))
    monkeypatch.setenv("WHOAMI_LEDGER", str(tmp_path / "l.jsonl"))
    monkeypatch.setenv("WHOAMI_BUDGET_SINCE", "2026-10-01T07:00:00Z")
    monkeypatch.setenv("GEMINI_BASE_URL", "http://fake/")
    settings = Settings.from_env()
    assert settings == Settings(
        env_file=tmp_path / "e",
        cache_dir=tmp_path / "c",
        ledger_path=tmp_path / "l.jsonl",
        budget_since=datetime(2026, 10, 1, 7, 0, tzinfo=UTC),
        base_url="http://fake/",
    )


def test_settings_from_env_defaults(monkeypatch):
    for name in ("WHOAMI_ENV_FILE", "WHOAMI_LLM_CACHE", "WHOAMI_LEDGER", "WHOAMI_BUDGET_SINCE", "GEMINI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env()
    assert settings.cache_dir == Path.home() / ".cache/whoami/llm"
    assert settings.ledger_path == Path.home() / ".cache/whoami/ledger.jsonl"
    assert settings.budget_since.tzinfo is not None
    assert settings.base_url == "https://generativelanguage.googleapis.com/v1beta/openai/"


def test_cache_key_ignores_dict_ordering(tmp_path: Path):
    cache = ResponseCache(tmp_path)
    assert cache.key({"a": 1, "b": 2}) == cache.key({"b": 2, "a": 1})
    assert cache.key({"a": 1}) != cache.key({"a": 2})


def test_cache_round_trips_a_value(tmp_path: Path):
    cache = ResponseCache(tmp_path)
    key = cache.key({"q": "ñ"})
    assert cache.get(key) is None
    cache.put(key, {"text": "hola"})
    assert cache.get(key) == {"text": "hola"}
    assert (tmp_path / key[:2] / f"{key}.json").exists()


def test_cache_corrupt_file_reads_as_a_miss(tmp_path: Path):
    cache = ResponseCache(tmp_path)
    key = cache.key({"q": 1})
    cache.put(key, {"text": "x"})
    (tmp_path / key[:2] / f"{key}.json").write_text("{not json")
    assert cache.get(key) is None


def test_cache_put_leaves_no_temp_files(tmp_path: Path):
    cache = ResponseCache(tmp_path)
    key = cache.key({"q": 1})
    cache.put(key, {"text": "x"})
    assert [p.name for p in (tmp_path / key[:2]).iterdir()] == [f"{key}.json"]


NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def make_ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger.jsonl", clock=lambda: NOW)


def test_ledger_appends_one_json_line_per_record(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    ledger.record(model="m", purpose="p", cache="miss", status="ok", latency_s=0.5, prompt_tokens=3, total_tokens=5)
    ledger.record(model="m", purpose="p", cache="hit", status="ok", latency_s=0.0)
    lines = (tmp_path / "ledger.jsonl").read_text().splitlines()
    first = json.loads(lines[0])
    assert len(lines) == 2
    assert first["ts"] == "2026-10-07T12:00:00Z"
    assert first["model"] == "m"
    assert first["prompt_tokens"] == 3
    assert first["total_tokens"] == 5


def test_ledger_spent_counts_chat_misses_since_the_window_start(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    old = Ledger(path, clock=lambda: datetime(2026, 10, 6, 6, 0, tzinfo=UTC))
    old.record(model="chat", purpose="p", cache="miss", status="ok", latency_s=0.1)
    ledger = make_ledger(tmp_path)
    ledger.record(model="chat", purpose="p", cache="miss", status="error:429", latency_s=0.1)
    ledger.record(model="chat", purpose="p", cache="hit", status="ok", latency_s=0.0)
    ledger.record(model="other", purpose="p", cache="miss", status="ok", latency_s=0.1)
    since = datetime(2026, 10, 6, 7, 0, tzinfo=UTC)
    assert ledger.spent("chat", since) == 1


def test_ledger_spent_sums_texts_of_sent_batches_and_one_unit_per_rejected_attempt(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    ledger.record(model="emb", purpose="p", cache="miss", status="ok", latency_s=0.1, n_texts=50)
    ledger.record(model="emb", purpose="p", cache="miss", status="error:500", latency_s=0.1, n_texts=20)
    ledger.record(model="emb", purpose="p", cache="hit", status="ok", latency_s=0.0, n_texts=7)
    assert ledger.spent("emb", NOW - timedelta(days=1)) == 51


def test_ledger_without_a_file_has_nothing_spent_and_an_empty_summary(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    assert ledger.spent("chat", NOW) == 0
    assert ledger.summary() == {}


def test_ledger_summary_aggregates_per_model(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    for latency in (1.0, 2.0, 3.0, 4.0):
        ledger.record(
            model="chat", purpose="p", cache="miss", status="ok", latency_s=latency,
            prompt_tokens=10, completion_tokens=5, total_tokens=15,
        )
    ledger.record(model="chat", purpose="p", cache="miss", status="error:429", latency_s=99.0)
    ledger.record(model="chat", purpose="p", cache="hit", status="ok", latency_s=0.0)
    ledger.record(model="emb", purpose="p", cache="miss", status="ok", latency_s=1.0, n_texts=9)
    summary = ledger.summary()
    assert summary["chat"] == {
        "calls": 5,
        "hits": 1,
        "errors": 1,
        "prompt_tokens": 40,
        "completion_tokens": 20,
        "total_tokens": 60,
        "texts": 0,
        "latency_p50_s": 2.5,
        "latency_p95_s": pytest.approx(3.85),
    }
    assert summary["emb"]["texts"] == 9


def test_ledger_summary_respects_since(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    ledger.record(model="chat", purpose="p", cache="miss", status="ok", latency_s=1.0)
    assert ledger.summary(since=NOW + timedelta(seconds=1)) == {}


class FakeTime:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_limiter(fake: FakeTime, rpm: int = 30, tpm: int = 1_000) -> RateLimiter:
    return RateLimiter(rpm=rpm, tpm=tpm, clock=fake.clock, sleep=fake.sleep)


def test_limiter_blocks_the_request_over_rpm_until_the_window_frees():
    fake = FakeTime()
    limiter = make_limiter(fake, rpm=30)
    for _ in range(30):
        limiter.acquire(1)
        fake.now += 1.0
    assert fake.sleeps == []
    limiter.acquire(1)
    assert fake.sleeps == [30.0]
    assert fake.now == 1060.0


def test_limiter_blocks_on_the_token_budget():
    fake = FakeTime()
    limiter = make_limiter(fake, rpm=100, tpm=1_000)
    limiter.acquire(600)
    fake.now += 10
    limiter.acquire(400)
    assert fake.sleeps == []
    limiter.acquire(300)
    assert fake.now == 1060.0


def test_limiter_lets_an_oversized_request_through_once_the_window_is_empty():
    fake = FakeTime()
    limiter = make_limiter(fake, tpm=1_000)
    limiter.acquire(5_000)
    assert fake.sleeps == []
    limiter.acquire(5_000)
    assert fake.now == 1060.0


def test_limiter_adjust_replaces_the_latest_estimate_with_the_actual_tokens():
    fake = FakeTime()
    limiter = make_limiter(fake, rpm=100, tpm=1_000)
    limiter.acquire(900)
    limiter.adjust(estimated=900, actual=100)
    limiter.acquire(900)
    assert fake.sleeps == []


CHAT = "gemini-3.1-flash-lite"
USER_MESSAGE = [{"role": "user", "content": "hola"}]


class HttpError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"http {status_code}")
        self.status_code = status_code


def chat_response(text: str | None = "respuesta", prompt: int = 10, completion: int = 5) -> SimpleNamespace:
    usage = SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion)
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))], usage=usage)


class FakeClient:
    """OpenAI-like client that replays scripted outcomes (responses or exceptions)."""

    def __init__(self, *outcomes) -> None:
        self.outcomes = list(outcomes)
        self.chat_calls: list[dict] = []
        self.embedding_calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create_chat))
        self.embeddings = SimpleNamespace(create=self._create_embeddings)

    def _next(self):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def _create_chat(self, **kwargs):
        self.chat_calls.append(kwargs)
        return self._next()

    def _create_embeddings(self, **kwargs):
        self.embedding_calls.append(kwargs)
        return self._next()


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        env_file=tmp_path / ".env",
        cache_dir=tmp_path / "cache",
        ledger_path=tmp_path / "ledger.jsonl",
        budget_since=NOW - timedelta(days=1),
        base_url="http://fake/",
    )


def make_llm(tmp_path: Path, client: FakeClient, fake: FakeTime | None = None, **kwargs) -> LLM:
    fake = fake or FakeTime()
    return LLM(
        client,
        make_settings(tmp_path),
        clock=lambda: NOW,
        monotonic=fake.clock,
        sleep=fake.sleep,
        jitter=lambda: 0.0,
        **kwargs,
    )


def ledger_lines(tmp_path: Path) -> list[dict]:
    path = tmp_path / "ledger.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_complete_returns_the_text_and_records_a_miss(tmp_path: Path):
    client = FakeClient(chat_response("hola mundo", prompt=10, completion=5))
    result = make_llm(tmp_path, client).complete(CHAT, USER_MESSAGE, purpose="test")
    assert isinstance(result, Completion)
    assert (result.text, result.model, result.cached) == ("hola mundo", CHAT, False)
    assert (result.prompt_tokens, result.completion_tokens) == (10, 5)
    [line] = ledger_lines(tmp_path)
    assert (line["cache"], line["status"], line["purpose"], line["total_tokens"]) == ("miss", "ok", "test", 15)


def test_complete_forwards_optional_arguments_only_when_given(tmp_path: Path):
    client = FakeClient(chat_response(), chat_response("{}"))
    llm = make_llm(tmp_path, client)
    llm.complete(CHAT, USER_MESSAGE, purpose="a")
    llm.complete(CHAT, USER_MESSAGE, purpose="b", response_format={"type": "json_object"}, max_tokens=50)
    plain, full = client.chat_calls
    assert plain == {"model": CHAT, "messages": USER_MESSAGE, "temperature": 0.0}
    assert full["response_format"] == {"type": "json_object"}
    assert full["max_tokens"] == 50


def test_identical_complete_is_served_from_the_cache(tmp_path: Path):
    client = FakeClient(chat_response("una vez"))
    llm = make_llm(tmp_path, client)
    first = llm.complete(CHAT, USER_MESSAGE, purpose="test")
    second = llm.complete(CHAT, USER_MESSAGE, purpose="test")
    assert len(client.chat_calls) == 1
    assert (second.text, second.cached) == ("una vez", True)
    assert (second.prompt_tokens, second.completion_tokens) == (first.prompt_tokens, first.completion_tokens)
    assert [(line["cache"], line["status"]) for line in ledger_lines(tmp_path)] == [("miss", "ok"), ("hit", "ok")]


def test_evidence_ids_order_does_not_change_the_cache_key_but_the_set_does(tmp_path: Path):
    client = FakeClient(chat_response("a"), chat_response("b"))
    llm = make_llm(tmp_path, client)
    llm.complete(CHAT, USER_MESSAGE, purpose="t", evidence_ids=["e2", "e1"])
    reordered = llm.complete(CHAT, USER_MESSAGE, purpose="t", evidence_ids=["e1", "e2", "e1"])
    other_set = llm.complete(CHAT, USER_MESSAGE, purpose="t", evidence_ids=["e1"])
    assert reordered.cached
    assert not other_set.cached
    assert len(client.chat_calls) == 2


def test_complete_json_parses_the_text_or_raises(tmp_path: Path):
    client = FakeClient(chat_response('{"tema": "economía"}'), chat_response("no es json"))
    llm = make_llm(tmp_path, client)
    assert llm.complete(CHAT, USER_MESSAGE, purpose="a").json() == {"tema": "economía"}
    with pytest.raises(LLMError):
        llm.complete(CHAT, [{"role": "user", "content": "otro"}], purpose="b").json()


@pytest.mark.parametrize(
    "text",
    [
        ' {\n  "tema": "economia",\n  "confianza": \n 0.95\n}\n```',
        '```json\n{"tema": "economia", "confianza": 0.95}\n```',
    ],
)
def test_completion_json_ignores_code_fences_around_the_value(text: str):
    completion = Completion(text, CHAT, False, 0, 0, 0.0)
    assert completion.json() == {"tema": "economia", "confianza": 0.95}


@pytest.mark.parametrize("model", ["gemma-4-31b-it", "gemini-3.8-flash", "gemini-embedding-2"])
def test_complete_rejects_unknown_and_non_chat_models(tmp_path: Path, model: str):
    client = FakeClient()
    with pytest.raises(ValueError):
        make_llm(tmp_path, client).complete(model, USER_MESSAGE, purpose="t")
    assert client.chat_calls == []


def capped_models(cap: int) -> dict[str, ModelLimits]:
    return {**MODELS, CHAT: replace(MODELS[CHAT], cap=cap)}


def seed_misses(tmp_path: Path, count: int, at: datetime, model: str = CHAT) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl", clock=lambda: at)
    for _ in range(count):
        ledger.record(model=model, purpose="seed", cache="miss", status="ok", latency_s=0.1)


def test_cap_exceeded_is_raised_before_any_network_call(tmp_path: Path):
    seed_misses(tmp_path, 2, NOW)
    client = FakeClient(chat_response())
    llm = make_llm(tmp_path, client, models=capped_models(2))
    with pytest.raises(CapExceeded, match=CHAT):
        llm.complete(CHAT, USER_MESSAGE, purpose="t")
    assert client.chat_calls == []
    assert (llm.spent(CHAT), llm.remaining(CHAT)) == (2, 0)


def test_misses_before_the_budget_window_do_not_count(tmp_path: Path):
    seed_misses(tmp_path, 2, NOW - timedelta(days=2))
    client = FakeClient(chat_response())
    llm = make_llm(tmp_path, client, models=capped_models(2))
    assert llm.complete(CHAT, USER_MESSAGE, purpose="t").text == "respuesta"
    assert (llm.spent(CHAT), llm.remaining(CHAT)) == (1, 1)


def test_cache_hits_ignore_the_cap(tmp_path: Path):
    client = FakeClient(chat_response())
    llm = make_llm(tmp_path, client, models=capped_models(1))
    llm.complete(CHAT, USER_MESSAGE, purpose="t")
    assert llm.complete(CHAT, USER_MESSAGE, purpose="t").cached


def test_429_twice_then_success_retries_with_growing_backoff(tmp_path: Path):
    fake = FakeTime()
    client = FakeClient(HttpError(429), HttpError(429), chat_response("ok"))
    result = make_llm(tmp_path, client, fake).complete(CHAT, USER_MESSAGE, purpose="t")
    assert result.text == "ok"
    assert fake.sleeps == [1.0, 2.0]
    assert [line["status"] for line in ledger_lines(tmp_path)] == ["error:429", "error:429", "ok"]
    assert {line["cache"] for line in ledger_lines(tmp_path)} == {"miss"}


def test_backoff_is_capped_at_sixty_seconds_plus_jitter(tmp_path: Path):
    fake = FakeTime()
    client = FakeClient(*[HttpError(503)] * 8)
    llm = LLM(
        client, make_settings(tmp_path), clock=lambda: NOW, monotonic=fake.clock, sleep=fake.sleep,
        jitter=lambda: 0.5, max_retries=7,
    )
    with pytest.raises(LLMError):
        llm.complete(CHAT, USER_MESSAGE, purpose="t")
    assert fake.sleeps == [1.5, 2.5, 4.5, 8.5, 16.5, 32.5, 60.5]


def test_retries_stop_after_max_retries(tmp_path: Path):
    client = FakeClient(*[HttpError(500)] * 3)
    llm = make_llm(tmp_path, client, max_retries=2)
    with pytest.raises(LLMError):
        llm.complete(CHAT, USER_MESSAGE, purpose="t")
    assert len(client.chat_calls) == 3


def test_a_retry_beyond_the_cap_raises_cap_exceeded(tmp_path: Path):
    client = FakeClient(HttpError(429), chat_response())
    llm = make_llm(tmp_path, client, models=capped_models(1))
    with pytest.raises(CapExceeded):
        llm.complete(CHAT, USER_MESSAGE, purpose="t")
    assert len(client.chat_calls) == 1


def test_a_400_error_raises_llm_error_without_retrying(tmp_path: Path):
    fake = FakeTime()
    client = FakeClient(HttpError(400), chat_response())
    with pytest.raises(LLMError) as raised:
        make_llm(tmp_path, client, fake).complete(CHAT, USER_MESSAGE, purpose="t")
    assert isinstance(raised.value.__cause__, HttpError)
    assert len(client.chat_calls) == 1
    assert fake.sleeps == []
    assert [line["status"] for line in ledger_lines(tmp_path)] == ["error:400"]


def test_an_exception_without_status_is_recorded_by_class_name(tmp_path: Path):
    client = FakeClient(ConnectionError("boom"))
    with pytest.raises(LLMError):
        make_llm(tmp_path, client).complete(CHAT, USER_MESSAGE, purpose="t")
    assert ledger_lines(tmp_path)[0]["status"] == "error:ConnectionError"


@pytest.mark.parametrize("content", [None, ""])
def test_empty_content_is_an_error_and_is_not_cached(tmp_path: Path, content):
    client = FakeClient(chat_response(content), chat_response("ya sí"))
    llm = make_llm(tmp_path, client)
    with pytest.raises(LLMError):
        llm.complete(CHAT, USER_MESSAGE, purpose="t")
    assert llm.complete(CHAT, USER_MESSAGE, purpose="t").text == "ya sí"
    assert len(client.chat_calls) == 2


def test_complete_waits_for_the_rate_limiter(tmp_path: Path):
    fake = FakeTime()
    client = FakeClient(*[chat_response() for _ in range(16)])
    llm = make_llm(tmp_path, client, fake)
    for index in range(16):
        llm.complete(CHAT, [{"role": "user", "content": str(index)}], purpose="t")
    assert fake.sleeps == [60.0]


EMBEDDING = "gemini-embedding-2"


def embedding_response(*vectors: list[float]) -> SimpleNamespace:
    return SimpleNamespace(data=[SimpleNamespace(embedding=vector, index=i) for i, vector in enumerate(vectors)])


def capped_embedding(cap: int) -> dict[str, ModelLimits]:
    return {**MODELS, EMBEDDING: replace(MODELS[EMBEDDING], cap=cap)}


def test_embed_returns_float32_vectors_in_input_order(tmp_path: Path):
    client = FakeClient(embedding_response([1, 0], [0, 1]))
    result = make_llm(tmp_path, client).embed(EMBEDDING, ["a", "b"], purpose="t", dimensions=2)
    assert result.dtype == np.float32
    assert result.tolist() == [[1.0, 0.0], [0.0, 1.0]]
    assert client.embedding_calls == [{"model": EMBEDDING, "input": ["a", "b"], "dimensions": 2}]
    [line] = ledger_lines(tmp_path)
    assert (line["cache"], line["status"], line["n_texts"]) == ("miss", "ok", 2)


def test_embed_with_a_partial_cache_hit_sends_only_the_missing_texts(tmp_path: Path):
    client = FakeClient(embedding_response([1, 0]), embedding_response([0, 1], [5, 5]))
    llm = make_llm(tmp_path, client)
    llm.embed(EMBEDDING, ["a"], purpose="t", dimensions=2)
    result = llm.embed(EMBEDDING, ["b", "a", "c"], purpose="t", dimensions=2)
    assert client.embedding_calls[1]["input"] == ["b", "c"]
    assert result.tolist() == [[0.0, 1.0], [1.0, 0.0], [5.0, 5.0]]
    hit = [line for line in ledger_lines(tmp_path) if line["cache"] == "hit"]
    assert [(line["n_texts"], line["status"]) for line in hit] == [(1, "ok")]


def test_embed_fully_cached_makes_no_call_and_one_hit_line(tmp_path: Path):
    client = FakeClient(embedding_response([1, 0], [0, 1]))
    llm = make_llm(tmp_path, client)
    llm.embed(EMBEDDING, ["a", "b"], purpose="t", dimensions=2)
    llm.embed(EMBEDDING, ["a", "b"], purpose="t", dimensions=2)
    assert len(client.embedding_calls) == 1
    assert [(line["cache"], line["n_texts"]) for line in ledger_lines(tmp_path)] == [("miss", 2), ("hit", 2)]


def test_embed_cache_is_keyed_by_dimensions(tmp_path: Path):
    client = FakeClient(embedding_response([1, 0]), embedding_response([1, 0, 0]))
    llm = make_llm(tmp_path, client)
    llm.embed(EMBEDDING, ["a"], purpose="t", dimensions=2)
    assert llm.embed(EMBEDDING, ["a"], purpose="t", dimensions=3).shape == (1, 3)


def test_embed_splits_into_batches(tmp_path: Path):
    client = FakeClient(embedding_response([1], [2]), embedding_response([3]))
    result = make_llm(tmp_path, client).embed(
        EMBEDDING, ["a", "b", "c"], purpose="t", dimensions=1, batch_size=2
    )
    assert [call["input"] for call in client.embedding_calls] == [["a", "b"], ["c"]]
    assert result.tolist() == [[1.0], [2.0], [3.0]]


def test_embed_cap_counts_texts_and_is_checked_before_each_batch(tmp_path: Path):
    client = FakeClient(embedding_response([1], [2]), embedding_response([3], [4]))
    llm = make_llm(tmp_path, client, models=capped_embedding(3))
    with pytest.raises(CapExceeded):
        llm.embed(EMBEDDING, ["a", "b", "c", "d"], purpose="t", dimensions=1, batch_size=2)
    assert len(client.embedding_calls) == 1
    assert (llm.spent(EMBEDDING), llm.remaining(EMBEDDING)) == (2, 1)


def test_embed_retries_a_429_and_counts_the_rejected_attempt_as_one_unit(tmp_path: Path):
    fake = FakeTime()
    client = FakeClient(HttpError(429), embedding_response([1], [2]))
    llm = make_llm(tmp_path, client, fake)
    llm.embed(EMBEDDING, ["a", "b"], purpose="t", dimensions=1)
    assert fake.sleeps == [1.0]
    assert llm.spent(EMBEDDING) == 3


def test_embed_rejects_chat_models_and_handles_no_texts(tmp_path: Path):
    llm = make_llm(tmp_path, FakeClient())
    with pytest.raises(ValueError):
        llm.embed(CHAT, ["a"], purpose="t")
    assert llm.embed(EMBEDDING, [], purpose="t", dimensions=4).shape == (0, 4)


def test_default_llm_builds_from_the_environment_without_calling_the_network(monkeypatch, tmp_path: Path):
    env_file = tmp_path / "fake.env"
    env_file.write_text("GEMINI_API_KEY=not-a-real-key\n")
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder")
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setenv("WHOAMI_ENV_FILE", str(env_file))
    monkeypatch.setenv("WHOAMI_LLM_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("WHOAMI_LEDGER", str(tmp_path / "ledger.jsonl"))
    assert isinstance(default_llm(), LLM)


def test_ledger_summary_renders_as_a_markdown_table(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    ledger.record(model="chat", purpose="p", cache="miss", status="ok", latency_s=1.0, total_tokens=15)
    lines = format_summary(ledger.summary()).splitlines()
    assert lines[0].startswith("| model | calls | hits")
    assert lines[1].startswith("|---")
    assert lines[2].startswith("| chat | 1 | 0 | 0 |")


def test_chat_limiter_keeps_headroom_under_the_published_rpm(tmp_path: Path):
    allowed = int(MODELS[CHAT].rpm * RATE_HEADROOM)
    client = FakeClient(*[chat_response() for _ in range(allowed + 1)])
    fake = FakeTime()
    llm = make_llm(tmp_path, client, fake)
    for n in range(allowed):
        llm.complete(CHAT, [{"role": "user", "content": f"q{n}"}], purpose="t")
    assert fake.sleeps == []
    llm.complete(CHAT, [{"role": "user", "content": "una más"}], purpose="t")
    assert fake.sleeps and fake.sleeps[0] > 0


def test_embedding_limiter_counts_texts_not_requests(tmp_path: Path):
    per_minute = int(MODELS[EMBEDDING].rpm * RATE_HEADROOM)
    client = FakeClient(embedding_response(*[[1]] * per_minute), embedding_response([1]))
    fake = FakeTime()
    llm = make_llm(tmp_path, client, fake)
    llm.embed(EMBEDDING, [f"t{n}" for n in range(per_minute)], purpose="t", dimensions=1, batch_size=per_minute)
    assert fake.sleeps == []
    llm.embed(EMBEDDING, ["uno más"], purpose="t", dimensions=1)
    assert fake.sleeps and fake.sleeps[0] > 0


class APITimeoutError(Exception):
    """Stands in for `openai.APITimeoutError`: retried by class name, it has no HTTP status."""


def test_complete_retries_a_timed_out_call(tmp_path: Path):
    fake = FakeTime()
    client = FakeClient(APITimeoutError("Request timed out."), chat_response("ok"))
    assert make_llm(tmp_path, client, fake).complete(CHAT, USER_MESSAGE, purpose="t").text == "ok"
    assert fake.sleeps == [1.0]


def test_schema_call_with_invalid_json_raises_and_is_not_cached(tmp_path: Path):
    schema = {"type": "json_schema", "json_schema": {"name": "x", "strict": True, "schema": {"type": "object"}}}
    client = FakeClient(chat_response(' {"juicios": [{"d": 1,' + " " * 200), chat_response('{"juicios": []}'))
    llm = make_llm(tmp_path, client)
    with pytest.raises(InvalidJSON):
        llm.complete(CHAT, USER_MESSAGE, purpose="t", response_format=schema)
    assert llm.complete(CHAT, USER_MESSAGE, purpose="t", response_format=schema).json() == {"juicios": []}
    assert len(client.chat_calls) == 2
