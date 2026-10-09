"""Live "Generar ficha": the batch generator for one group, on the app's own Gemini client, quota and cache."""

import asyncio

from whoami.backend.gemini import GeminiClient
from whoami.backend.gemini_completions import CompletionUnavailable, GeminiCompletions
from whoami.backend.repository import EditorialRepository, MissingRecord
from whoami.generation.case_files import NoGroundedClaims, TwoStepGenerator, generate_case_file
from whoami.generation.jsonschemas import to_claims
from whoami.schemas import Evidence, Group

PROMPT_VERSION = "case-file-1"

__all__ = ["CompletionUnavailable", "LiveCaseFiles", "NoGroundedClaims"]


def ensure_claims(data: dict) -> None:
    to_claims(data)


class LiveCaseFiles:
    def __init__(self, repository: EditorialRepository, gemini: GeminiClient) -> None:
        self._repository = repository
        self._gemini = gemini

    async def generate(self, group_id: str) -> str:
        """Generates, verifies and saves the case file of a group; returns its id.

        Raises `CompletionUnavailable` when Gemini fails and `NoGroundedClaims` when the sources back no claim."""
        loop = asyncio.get_running_loop()
        return await asyncio.to_thread(self._generate, group_id, loop)

    def _generate(self, group_id: str, loop: asyncio.AbstractEventLoop) -> str:
        group = Group.model_validate(self._repository.record("group", group_id))
        generator = TwoStepGenerator(GeminiCompletions(self._gemini, loop, prompt_version=PROMPT_VERSION,
                                                       validators={"afirmaciones": ensure_claims}), self._gemini.settings.generation_model)
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
