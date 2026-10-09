"""Live query box: the batch `answer_query` on the app's own retrieval, Gemini client, quota and cache."""

import asyncio
import hashlib
from collections.abc import Mapping

from whoami.backend.gemini import GeminiClient
from whoami.backend.gemini_completions import CompletionUnavailable, GeminiCompletions
from whoami.backend.retrieval import CorpusRetriever
from whoami.generation.prompting import GateDecision
from whoami.generation.query_box import TASK, answer_query
from whoami.schemas import Evidence

PROMPT_VERSION = "query-2"
# People type keywords into the search box; for those, what the sources say about the topic is the answer.
LIVE_TASK = TASK + (
    " Si la consulta no es una pregunta sino palabras clave o un tema, usa estado=respondida y resume en una o dos frases "
    "lo que dicen las fuentes sobre ese tema, con citas literales. Abstente solo si ninguna fuente trata el tema. "
    "Si es una pregunta, respóndela o abstente: nunca la sustituyas por un resumen del tema."
)

__all__ = ["CompletionUnavailable", "LiveQueries"]


class _CorpusGate:
    """Abstains before the model when no evidence is related to the query."""

    def __init__(self, corpus: CorpusRetriever) -> None:
        self._corpus = corpus

    def decide(self, query: str) -> GateDecision:
        if self._corpus.related(query, 1):
            return GateDecision(True)
        return GateDecision(False, "ninguna fuente se parece lo bastante a la consulta", f"Fuentes que respondan directamente: {query}")


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
        answer = answer_query(identifier, question, self._corpus, self._gate, self._evidence, llm, self._gemini.settings.gemini_model, task=LIVE_TASK)
        return answer.model_dump(mode="json")
