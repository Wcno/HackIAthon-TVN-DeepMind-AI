"""Provider failures use controlled transports, never a live API key."""

import asyncio
from dataclasses import replace

import httpx
import pytest

from whoami.backend.gemini import GeminiClient, GenerationUnavailable
from whoami.backend.repository import EditorialRepository
from whoami.backend.settings import Settings


MESSAGES = [{"role": "user", "content": "Return a JSON answer using the supplied evidence."}]
EVIDENCE = {"N-1": {"titulo": "A source headline"}}


def validate(value):
    if not isinstance(value.get("answer"), str):
        raise ValueError("Invalid answer")


def test_429_and_503_retry_then_cache_survives_restart(tmp_path):
    async def scenario():
        attempts = []

        def handler(request):
            attempts.append(request)
            if len(attempts) <= 2:
                return httpx.Response([429, 503][len(attempts) - 1], headers={"Retry-After": "0"})
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"answer":"supported"}'}}]})

        settings = Settings(database=tmp_path / "db.sqlite3", offline=False, gemini_api_key="test-secret")
        client = GeminiClient(EditorialRepository(settings.database), settings, transport=httpx.MockTransport(handler))
        result = await client.generate(MESSAGES, EVIDENCE, validate=validate)
        assert result.attempts == 3 and not result.cached
        await client.close()
        offline = GeminiClient(EditorialRepository(settings.database), replace(settings, offline=True), transport=httpx.MockTransport(handler))
        cached = await offline.generate(MESSAGES, EVIDENCE, validate=validate)
        assert cached.content == result.content and cached.cached
        assert len(attempts) == 3
        for messages, evidence, version in (
            ([{"role": "user", "content": "Different prompt"}], EVIDENCE, "1"),
            (MESSAGES, {"N-1": {"titulo": "Changed evidence"}}, "1"),
            (MESSAGES, EVIDENCE, "2"),
        ):
            with pytest.raises(GenerationUnavailable, match="Offline"):
                await offline.generate(messages, evidence, validate=validate, prompt_version=version)
        await offline.close()

    asyncio.run(scenario())


def test_deadline_caps_slow_requests_and_retry_after(tmp_path):
    async def scenario():
        attempts = 0

        async def handler(request):
            nonlocal attempts
            attempts += 1
            return httpx.Response(429, headers={"Retry-After": "3600"})

        settings = Settings(database=tmp_path / "db.sqlite3", offline=False, gemini_api_key="test-secret", generation_timeout=0.03)
        client = GeminiClient(EditorialRepository(settings.database), settings, transport=httpx.MockTransport(handler))
        with pytest.raises(GenerationUnavailable, match="deadline"):
            await client.generate(MESSAGES, EVIDENCE, validate=validate)
        assert attempts == 1
        await client.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("response", [httpx.Response(503), httpx.Response(401, text="test-secret"),
                                    httpx.Response(200, json={"choices": [{"message": {"content": "[]"}}]}),
                                    httpx.Response(200, json={"choices": [{"message": {"content": '{"wrong":true}'}}]})])
def test_final_and_invalid_responses_do_not_enter_cache_or_expose_secrets(tmp_path, response):
    async def scenario():
        settings = Settings(database=tmp_path / "db.sqlite3", offline=False, gemini_api_key="test-secret", generation_attempts=1)
        repository = EditorialRepository(settings.database)
        client = GeminiClient(repository, settings, transport=httpx.MockTransport(lambda _: response))
        with pytest.raises(GenerationUnavailable) as error:
            await client.generate(MESSAGES, EVIDENCE, validate=validate)
        assert "test-secret" not in str(error.value)
        with repository.connection() as connection:
            assert connection.execute("SELECT count(*) FROM generation_cache").fetchone()[0] == 0
        await client.close()

    asyncio.run(scenario())
