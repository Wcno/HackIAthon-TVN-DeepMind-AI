"""Every word of a structured answer comes from explicitly cited claims."""

import pytest

from generation_fakes import FakeLLM, by_id, news
from whoami.generation.prompting import CosineGate
from whoami.generation.query_box import answer_query
from whoami.schemas import Answer, Citation, Claim


class Retriever:
    def search(self, query, k):
        return [("N-1", 0.9)]


EVIDENCE = by_id(news("N-1", titulo="El Canal tendrá 33 tránsitos diarios desde el 15 de octubre de 2026."))
CITATION = {"id_evidencia": "N-1", "campo": "titulo", "pasaje": "33 tránsitos diarios"}


def structured_payload(**overrides):
    return {"estado": "respondida", "respuesta": "Extra uncited assertion must be ignored.", "citas": [],
            "afirmaciones": [{"texto": "El Canal tendrá 33 tránsitos diarios.", "tipo": "hecho", "atribuida_a": None,
                              "citas": [CITATION]}],
            "versiones": [], "motivo_abstencion": None, "faltante": None, **overrides}


def ask(payload):
    retriever = Retriever()
    return answer_query("Q-1", "¿Cuántos tránsitos tendrá el Canal?", retriever, CosineGate(retriever), EVIDENCE,
                        FakeLLM([payload]), "gemini-3.5-flash-lite", structured=True)


def test_free_text_cannot_add_facts_outside_the_claim_map():
    answer = ask(structured_payload())
    assert answer.respuesta == "El Canal tendrá 33 tránsitos diarios."
    assert len(answer.afirmaciones) == 1
    assert answer.citas[0].pasaje == CITATION["pasaje"]


def test_a_structured_answer_without_claims_abstains_even_if_legacy_text_has_citations():
    payload = structured_payload(afirmaciones=[], respuesta="El Canal tendrá 33 tránsitos diarios.", citas=[CITATION])
    assert ask(payload).estado == "abstencion"


def test_unsupported_claims_cannot_supply_response_text():
    payload = structured_payload()
    payload["afirmaciones"][0]["texto"] = "El Canal tendrá 99 tránsitos diarios."
    assert ask(payload).estado == "abstencion"


def test_saved_structured_answers_cannot_mismatch_their_claims():
    claim = Claim(id_afirmacion="A-1", texto="El Canal tendrá 33 tránsitos diarios.", tipo="hecho", citas=(Citation(**CITATION),))
    with pytest.raises(ValueError, match="afirmaciones"):
        Answer(id_consulta="Q-1", consulta="¿Cuántos?", estado="respondida", respuesta="Texto sin vínculo.",
               citas=claim.citas, afirmaciones=(claim,))


def test_supported_claim_survives_without_the_unsupported_neighbor():
    payload = structured_payload()
    payload["afirmaciones"].append({"texto": "El Canal tendrá 99 tránsitos diarios.", "tipo": "hecho", "atribuida_a": None,
                                    "citas": [CITATION]})
    answer = ask(payload)
    assert answer.respuesta == "El Canal tendrá 33 tránsitos diarios."
    assert len(answer.afirmaciones) == 1


def test_structured_claims_cannot_cite_outside_the_retrieved_evidence():
    payload = structured_payload()
    payload["afirmaciones"][0]["citas"] = [CITATION | {"id_evidencia": "N-404"}]
    assert ask(payload).estado == "abstencion"
