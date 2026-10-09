"""Live query box: the batch `answer_query` on the app's own retrieval, Gemini client, quota and cache."""

import asyncio
import hashlib
from collections.abc import Mapping

from whoami.backend.gemini import GeminiClient
from whoami.backend.gemini_completions import CompletionUnavailable, GeminiCompletions
from whoami.backend.retrieval import CorpusRetriever
from whoami.generation.prompting import CosineGate, GateDecision
from whoami.generation.query_box import answer_query
from whoami.schemas import Evidence

PROMPT_VERSION = "query-1"

__all__ = ["CompletionUnavailable", "LiveQueries"]


class _CosineView:
    """The corpus' embedding cosines as the `Retriever` the cosine gate reads."""

    def __init__(self, corpus: CorpusRetriever) -> None:
        self._corpus = corpus

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        return self._corpus.cosine_search(query, k) or []


class _CorpusGate:
    """Abstains on questions no source resembles. Without embeddings (BM25 only) the verifier is the safeguard."""

    def __init__(self, corpus: CorpusRetriever) -> None:
        self._corpus = corpus
        self._cosine = CosineGate(_CosineView(corpus))

    def decide(self, query: str) -> GateDecision:
        if self._corpus.cosine_search(query, 1) is None:
            return GateDecision(True)
        return self._cosine.decide(query)


class LiveQueries:
    def __init__(self, gemini: GeminiClient, corpus: CorpusRetriever, evidence: Mapping[str, dict]) -> None:
        self._gemini = gemini
        self._corpus = corpus
        self._gate = _CorpusGate(corpus)
        self._evidence = {key: Evidence.model_validate(value) for key, value in evidence.items()}

    async def answer(self, question: str) -> dict:
        """The verified answer to a question, as an `Answer` record.

        Raises `CompletionUnavailable` when Gemini fails, so that is never mistaken for an abstention."""
        loop = asyncio.get_running_loop()
        return await asyncio.to_thread(self._answer, question, loop)

    def _answer(self, question: str, loop: asyncio.AbstractEventLoop) -> dict:
        llm = GeminiCompletions(self._gemini, loop, prompt_version=PROMPT_VERSION)
        identifier = "Q-live-" + hashlib.sha256(question.encode()).hexdigest()[:12]
        answer = answer_query(identifier, question, self._corpus, self._gate, self._evidence, llm, self._gemini.settings.generation_model)
        return answer.model_dump(mode="json")
