"""Generation quota behavior at the public Gemini transport boundary."""
import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from whoami.backend.gemini import GeminiClient, GenerationUnavailable
from whoami.backend.repository import EditorialRepository
from whoami.backend.settings import Settings
from whoami.llm.ledger import Ledger
from whoami.llm.models import MODELS, ModelLimits


def test_production_budget_reserves_free_tier_not_forty_percent_of_an_already_reduced_cap(tmp_path):
    from whoami.backend.quota import GenerationQuota, QuotaUnavailable
    path = tmp_path / "shared.jsonl"
    ledger = Ledger(path, lambda: datetime.now(UTC) - timedelta(minutes=2))
    for _ in range(MODELS["gemini-3.5-flash-lite"].cap - 8):
        ledger.record(model="gemini-3.5-flash-lite", purpose="other-tests", cache="miss", status="ok", latency_s=0)
    quota = GenerationQuota("gemini-3.5-flash-lite", ledger_path=path, database=tmp_path / "quota.sqlite3")
    for _ in range(8):
        quota.reserve(1)
    with pytest.raises(QuotaUnavailable):
        quota.reserve(1)


def test_budget_survives_restart_and_cache_is_free(tmp_path):
    async def scenario():
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"answer":"ok"}'}}]})
        settings = Settings(database=tmp_path / "editor.db", offline=False, gemini_api_key="fake")
        options = {"transport": httpx.MockTransport(handler), "quota_limits": ModelLimits(settings.gemini_model, 100, 100000, 5, "chat")}
        client = GeminiClient(EditorialRepository(settings.database), settings, **options)
        await client.generate([{"role": "user", "content": "one"}], {}, validate=lambda _: None)
        await client.close()
        client = GeminiClient(EditorialRepository(settings.database), settings, **options)
        assert (await client.generate([{"role": "user", "content": "one"}], {}, validate=lambda _: None)).cached
        await client.generate([{"role": "user", "content": "two"}], {}, validate=lambda _: None)
        with pytest.raises(GenerationUnavailable, match="quota"):
            await client.generate([{"role": "user", "content": "three"}], {}, validate=lambda _: None)
        assert len(calls) == 2
        await client.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("response", [httpx.Response(429, headers={"Retry-After": "0"}),
                                      httpx.Response(200, json={"choices": [{"message": {"content": "[]"}}]})])
def test_failed_attempts_consume_budget_before_retry(tmp_path, response):
    async def scenario():
        calls = []
        def handler(request):
            calls.append(request)
            return response
        settings = Settings(database=tmp_path / "editor.db", offline=False, gemini_api_key="fake")
        client = GeminiClient(EditorialRepository(settings.database), settings,
                              transport=httpx.MockTransport(handler),
                              quota_limits=ModelLimits(settings.gemini_model, 100, 100000, 3, "chat"))
        with pytest.raises(GenerationUnavailable):
            await client.generate([], {}, validate=lambda _: None)
        with pytest.raises(GenerationUnavailable, match="quota"):
            await client.generate([], {}, validate=lambda _: None)
        assert len(calls) == 1
        await client.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("tokens,rpm,tpm,cap", [(0, 1, 100000, 100), (700, 100, 2000, 100), (0, 100, 100000, 3)])
def test_project_calls_share_budget_and_recent_rate_limits(tmp_path, tokens, rpm, tpm, cap):
    async def scenario():
        settings = Settings(database=tmp_path / "editor.db", offline=False, gemini_api_key="fake")
        ledger = tmp_path / "project.jsonl"
        Ledger(ledger, lambda: datetime.now(UTC)).record(model=settings.gemini_model, purpose="other-tests", cache="miss", status="ok", latency_s=0, total_tokens=tokens)
        calls = []
        client = GeminiClient(EditorialRepository(settings.database), settings,
                              transport=httpx.MockTransport(lambda request: calls.append(request)), ledger_path=ledger,
                              quota_limits=ModelLimits(settings.gemini_model, rpm, tpm, cap, "chat"))
        with pytest.raises(GenerationUnavailable, match="quota"):
            await client.generate([], {}, validate=lambda _: None)
        assert calls == []
        await client.close()
    asyncio.run(scenario())


def test_simultaneous_clients_cannot_spend_last_reservation_twice(tmp_path):
    async def scenario():
        settings = Settings(database=tmp_path / "editor.db", offline=False, gemini_api_key="fake")
        calls = []
        async def handler(request):
            calls.append(request)
            await asyncio.sleep(0.02)
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
        clients = [GeminiClient(EditorialRepository(settings.database), settings, transport=httpx.MockTransport(handler),
                               quota_limits=ModelLimits(settings.gemini_model, 100, 100000, 3, "chat")) for _ in range(2)]
        results = await asyncio.gather(*(client.generate([], {}, validate=lambda _: None) for client in clients), return_exceptions=True)
        assert sum(isinstance(result, GenerationUnavailable) for result in results) == 1
        assert len(calls) == 1
        for client in clients:
            await client.close()
    asyncio.run(scenario())


def test_response_options_are_sent_and_separate_cache_entries(tmp_path):
    async def scenario():
        settings = Settings(database=tmp_path / "editor.db", offline=False, gemini_api_key="fake")
        requests = []
        def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}],
                                           "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}})
        client = GeminiClient(EditorialRepository(settings.database), settings, transport=httpx.MockTransport(handler))
        await client.generate([], {}, validate=lambda _: None)
        await client.generate([], {}, validate=lambda _: None, response_format={"type": "json_schema"}, max_tokens=42)
        assert requests[0]["max_tokens"] == 1000
        assert requests[1]["max_tokens"] == 42
        assert requests[1]["response_format"] == {"type": "json_schema"}
        summary = Ledger(settings.database.with_suffix(".ledger.jsonl"), lambda: datetime.now(UTC)).summary()
        assert summary[settings.gemini_model]["total_tokens"] == 14
        await client.close()
    asyncio.run(scenario())
