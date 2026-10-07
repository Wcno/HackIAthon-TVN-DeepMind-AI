"""Smoke test of the Gemini free tier as decided in docs/adr/0001."""

import json
import os
import sys
import time
from collections.abc import Callable

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_DIMENSIONS = 768
BATCH_PROBE_SIZE = 10
TOPICS = [
    "economía",
    "logística/Canal",
    "turismo",
    "servicios públicos",
    "eventos naturales",
    "regulación",
]
TOPIC_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "clasificacion",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "tema": {"type": "string", "enum": TOPICS},
                "confianza": {"type": "number"},
            },
            "required": ["tema", "confianza"],
            "additionalProperties": False,
        },
    },
}
HEADLINE = "Canal de Panamá restringe tránsitos por sequía"
SAME_EVENT = [
    "Canal de Panamá restringe tránsitos por sequía",
    "La sequía obliga al Canal a limitar el paso de buques",
]
UNRELATED = "Selección de fútbol de Panamá anuncia su convocatoria"

load_dotenv()
client = OpenAI(api_key=os.environ["GEMINI_API_KEY"], base_url=BASE_URL)


def chat_ok() -> str:
    response = client.chat.completions.create(
        model="gemini-3.5-flash-lite",
        messages=[{"role": "user", "content": "Responde solo: ok"}],
    )
    content = response.choices[0].message.content or ""
    assert "ok" in content.lower(), f"unexpected reply: {content!r}"
    return f"reply={content.strip()!r} tokens={response.usage.total_tokens}"


def strict_json(model: str) -> Callable[[], str]:
    def check() -> str:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Clasifica el titular en un tema."},
                {"role": "user", "content": HEADLINE},
            ],
            response_format=TOPIC_SCHEMA,
        )
        parsed = json.loads(response.choices[0].message.content)
        assert parsed["tema"] in TOPICS, f"tema outside enum: {parsed}"
        return f"{parsed} tokens={response.usage.total_tokens}"

    return check


def embeddings() -> str:
    texts = [*SAME_EVENT, UNRELATED]
    response = client.embeddings.create(
        model=EMBEDDING_MODEL, input=texts, dimensions=EMBEDDING_DIMENSIONS
    )
    vectors = np.array([item.embedding for item in response.data])
    assert vectors.shape == (3, EMBEDDING_DIMENSIONS), f"shape {vectors.shape}"
    unit = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    same, cross_a, cross_b = unit[0] @ unit[1], unit[0] @ unit[2], unit[1] @ unit[2]
    assert same > max(cross_a, cross_b), "same-event pair is not the most similar"
    return f"cos same={same:.3f} unrelated={cross_a:.3f}/{cross_b:.3f}"


def embeddings_batch_quota() -> str:
    """One request with 10 inputs: compare the RPD counter in AI Studio before and after (+1 or +10)."""
    texts = [f"{HEADLINE} ({index})" for index in range(BATCH_PROBE_SIZE)]
    response = client.embeddings.create(
        model=EMBEDDING_MODEL, input=texts, dimensions=EMBEDDING_DIMENSIONS
    )
    assert len(response.data) == BATCH_PROBE_SIZE, f"got {len(response.data)} vectors"
    sent_at = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    tokens = response.usage.total_tokens if response.usage else "not reported"
    return f"sent_at={sent_at} vectors={len(response.data)} tokens={tokens}"


def run(name: str, check: Callable[[], str]) -> bool:
    start = time.perf_counter()
    try:
        detail = check()
        passed = True
    except Exception as error:
        status = getattr(error, "status_code", "")
        detail = f"{type(error).__name__} {status} {error}"
        passed = False
    elapsed_ms = (time.perf_counter() - start) * 1000
    print(f"{'PASS' if passed else 'FAIL'} {name} {elapsed_ms:.0f}ms {detail}")
    return passed


checks = {
    "chat gemini-3.5-flash-lite": chat_ok,
    "strict json gemini-3.5-flash-lite": strict_json("gemini-3.5-flash-lite"),
    "strict json gemini-3.8-flash": strict_json("gemini-3.8-flash"),
    f"embeddings {EMBEDDING_MODEL}": embeddings,
    f"embeddings batch quota {EMBEDDING_MODEL}": embeddings_batch_quota,
}
selected = sys.argv[1:]
results = [
    run(name, check)
    for name, check in checks.items()
    if not selected or any(term in name for term in selected)
]
print(f"{sum(results)}/{len(results)} PASS")
