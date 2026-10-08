"""Live "Generar ficha": the batch generator for one group, on the app's own Gemini client, quota and cache."""

import asyncio
import json
from collections.abc import Iterable

from whoami.backend.gemini import GeminiClient, GenerationUnavailable
from whoami.backend.repository import EditorialRepository, MissingRecord
from whoami.generation.case_files import NoGroundedClaims, TwoStepGenerator, generate_case_file
from whoami.generation.jsonschemas import to_claims
from whoami.llm.client import Completion
from whoami.schemas import Evidence, Group

PROMPT_VERSION = "case-file-1"

__all__ = ["CaseFileUnavailable", "LiveCaseFiles", "NoGroundedClaims"]


class CaseFileUnavailable(Exception):
    """Gemini could not answer (connection, quota or an unusable reply): nothing was saved and trying again is safe.

    Deliberately not an `LLMError`, which the generator would read as "the sources back no claims"."""


def ensure_claims(data: dict) -> None:
    to_claims(data)


class GeminiCompletions:
    """The `LLM.complete` the generator expects, answered by the app's async Gemini client from a worker thread."""

    def __init__(self, gemini: GeminiClient, loop: asyncio.AbstractEventLoop) -> None:
        self._gemini = gemini
        self._loop = loop

    def complete(self, model: str, messages: list[dict], *, purpose: str, evidence_ids: Iterable[str] = (),
                 response_format: dict | None = None, temperature: float = 0.0, max_tokens: int | None = None) -> Completion:
        # An unusable claims reply must not be cached, or retrying would only replay it.
        validate = ensure_claims if purpose == "afirmaciones" else (lambda data: None)
        request = self._gemini.generate(messages, {}, validate=validate, prompt_version=PROMPT_VERSION, temperature=temperature,
                                        response_format=response_format, max_tokens=max_tokens or 1000)
        try:
            result = asyncio.run_coroutine_threadsafe(request, self._loop).result()
        except GenerationUnavailable as error:
            raise CaseFileUnavailable(str(error)) from error
        return Completion(json.dumps(result.content, ensure_ascii=False), model, result.cached, 0, 0, 0.0)


class LiveCaseFiles:
    def __init__(self, repository: EditorialRepository, gemini: GeminiClient) -> None:
        self._repository = repository
        self._gemini = gemini

    async def generate(self, group_id: str) -> str:
        """Generates, verifies and saves the case file of a group; returns its id.

        Raises `CaseFileUnavailable` when Gemini fails and `NoGroundedClaims` when the sources back no claim."""
        loop = asyncio.get_running_loop()
        return await asyncio.to_thread(self._generate, group_id, loop)

    def _generate(self, group_id: str, loop: asyncio.AbstractEventLoop) -> str:
        group = Group.model_validate(self._repository.record("group", group_id))
        generator = TwoStepGenerator(GeminiCompletions(self._gemini, loop), self._gemini.settings.gemini_model)
        case_file = generate_case_file(generator, group, self._sources_of(group))
        return self._repository.add_generated_case(case_file.model_dump(mode="json"))

    def _sources_of(self, group: Group) -> dict[str, Evidence]:
        ids = [member.id_noticia for member in group.miembros] + [link.id_evidencia for link in group.contexto]
        sources = {}
        for evidence_id in ids:
            try:
                sources[evidence_id] = Evidence.model_validate(self._repository.record("evidence", evidence_id))
            except MissingRecord:
                continue
        return sources
