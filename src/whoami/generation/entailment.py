"""Optional check that the passages a claim cites actually support it, one model call per claim.

The verifier already proves a passage is literal and its figures are in the source; this asks whether the
passage says what the claim says. A model that cannot answer is not a reason to drop a claim.
"""

from collections.abc import Mapping
from typing import Literal

from whoami.generation.jsonschemas import entailment_schema, response_format
from whoami.generation.prompting import build_messages
from whoami.generation.untrusted import neutralize
from whoami.llm.client import CapExceeded, LLMError
from whoami.schemas import Claim, Evidence

Verdict = Literal["respaldada", "parcial", "no_respaldada", "error"]

PURPOSE = "g4-implicacion"
MAX_TOKENS = 200
ENTAILMENT_TASK = (
    "Decide si los pasajes citados respaldan la afirmación. "
    "respaldada: todo lo que afirma está en los pasajes; "
    "parcial: una parte no está; "
    "no_respaldada: los pasajes no la sostienen o la contradicen. "
    "Una inferencia o hipótesis está respaldada si se presenta como tal y se apoya en los pasajes."
)
_VERDICTS = ("respaldada", "parcial", "no_respaldada")


class EntailmentChecker:
    def __init__(self, llm, model: str) -> None:
        self._llm = llm
        self._model = model

    def check(self, claim: Claim, evidences: Mapping[str, Evidence]) -> Verdict:
        cited_ids = list(dict.fromkeys(citation.id_evidencia for citation in claim.citas))
        passages = "\n".join(f"- {c.id_evidencia} [{c.campo}]: {neutralize(c.pasaje)}" for c in claim.citas)
        messages = build_messages(
            f"{ENTAILMENT_TASK}\nPasajes citados:\n{passages}",
            [evidences[i] for i in cited_ids if i in evidences],
            user_query=f"Afirmación ({claim.tipo}): {claim.texto}",
        )
        try:
            completion = self._llm.complete(
                self._model,
                messages,
                purpose=PURPOSE,
                evidence_ids=cited_ids,
                response_format=response_format(PURPOSE, entailment_schema()),
                max_tokens=MAX_TOKENS,
            )
            verdict = completion.json()["veredicto"]
        except CapExceeded:
            raise
        except (LLMError, KeyError, TypeError):
            return "error"
        return verdict if verdict in _VERDICTS else "error"
