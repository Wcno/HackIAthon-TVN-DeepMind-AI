import json
from datetime import UTC, datetime, timedelta

import numpy as np

from whoami.pipeline.ai import CountingLLM, ai_components

CUTOFF = datetime(2026, 10, 7, 12, tzinfo=UTC)


class FakeCompletion:
    def __init__(self, value, cached):
        self._value = value
        self.cached = cached

    def json(self):
        if isinstance(self._value, Exception):
            raise self._value
        return self._value


class FakeLLM:
    def __init__(self, same_event=False):
        self.same_event = same_event
        self.calls = []

    def complete(self, model, messages, *, purpose, **options):
        self.calls.append(purpose)
        answer = {"tema": "turismo", "confianza": 0.8} if purpose == "g3-tema-llm" else {"mismo_hecho": self.same_event}
        return FakeCompletion(answer, cached=len(self.calls) % 2 == 0)


def stamp(hours_ago):
    return (CUTOFF - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def row(news_id, title, hours_ago):
    return {"id_noticia": news_id, "titulo": title, "descripcion": "", "fecha_publicacion": stamp(hours_ago)}


def cosine_vectors(cosine):
    angle = np.arccos(cosine)
    return np.array([[1.0, 0.0], [np.cos(angle), np.sin(angle)]])


def test_counting_llm_counts_cache_hits_and_misses_per_purpose():
    llm = CountingLLM(FakeLLM())

    for _ in range(3):
        llm.complete("m", [], purpose="a")
    llm.complete("m", [], purpose="b")

    assert llm.counts() == {"a": (1, 2), "b": (1, 0)}


def test_the_judge_decides_grey_zone_pairs_when_there_is_an_llm():
    rows = [row("N-1", "Cierran el puente", 5), row("N-2", "Reabren el puente", 4)]
    vectors = cosine_vectors(0.72)

    _, group = ai_components(FakeLLM(same_event=True), "gemma")(rows, vectors)
    _, group_apart = ai_components(FakeLLM(same_event=False), "gemma")(rows, vectors)

    dates = [datetime.fromisoformat(r["fecha_publicacion"]) for r in rows]
    assert group(vectors, dates) == [[0, 1]]
    assert group_apart(vectors, dates) == [[0], [1]]


def test_without_an_llm_the_grouping_uses_embeddings_only():
    rows = [row("N-1", "Cierran el puente", 5), row("N-2", "Reabren el puente", 4)]
    vectors = cosine_vectors(0.72)

    _, group = ai_components(None, "gemma")(rows, vectors)

    dates = [datetime.fromisoformat(r["fecha_publicacion"]) for r in rows]
    assert group(vectors, dates) == [[0], [1]]


def test_the_classifier_is_trained_on_the_labeled_headlines_and_asks_the_llm_when_it_doubts(tmp_path):
    labels = tmp_path / "temas.jsonl"
    items = [("N-1", "economia"), ("N-2", "economia"), ("N-3", "turismo"), ("N-4", "turismo")]
    labels.write_text("\n".join(json.dumps({"id_noticia": i, "tema": t}) for i, t in items), encoding="utf-8")
    rows = [row(f"N-{n}", f"Titular {n}", n) for n in range(1, 6)]
    vectors = np.array([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [0.1, 0.9], [0.7, 0.7]])
    llm = FakeLLM()

    classify, _ = ai_components(llm, "gemma", labels)(rows, vectors)
    results = classify(rows, vectors)

    assert [method for _, _, method in results] == ["embeddings"] * 4 + ["llm"]
    assert results[4][0] == "turismo"
    assert llm.calls == ["g3-tema-llm"]


def test_without_an_llm_every_topic_comes_from_embeddings(tmp_path):
    labels = tmp_path / "temas.jsonl"
    labels.write_text(
        "\n".join(json.dumps({"id_noticia": f"N-{n}", "tema": t}) for n, t in [(1, "economia"), (2, "turismo")]),
        encoding="utf-8",
    )
    rows = [row("N-1", "a", 1), row("N-2", "b", 2), row("N-3", "c", 3)]
    vectors = np.array([[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]])

    classify, _ = ai_components(None, "gemma", labels)(rows, vectors)

    assert {method for _, _, method in classify(rows, vectors)} == {"embeddings"}
