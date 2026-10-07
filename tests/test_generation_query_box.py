import pytest

from generation_fakes import FakeLLM, LLMError, by_id, indicator, news
from whoami.generation.prompting import RetrievalGate
from whoami.generation.query_box import UNVERIFIABLE_REASON, INVALID_ANSWER_REASON, answer_query
from whoami.generation.retrieval import BM25Index, BM25Retriever, documents_from

TRANSITS = "La Autoridad del Canal de Panamá informó que limitará a 32 los tránsitos diarios a partir del 12 de octubre."
EVIDENCES = by_id(
    news("N-1", titulo="El Canal reduce los tránsitos diarios", descripcion=TRANSITS),
    news("N-2", titulo="Inflación de 1,1 % en septiembre", descripcion="Analistas citan una inflación anual de 1,1 % en septiembre."),
    news("N-3", titulo="Inflación de 2,3 % en septiembre", descripcion="Un informe privado ubica la inflación anual en 2,3 % en septiembre."),
    indicator(),
)
RETRIEVER = BM25Retriever(BM25Index(documents_from(EVIDENCES.values())))
GATE = RetrievalGate(min_top_score=0.5, min_hits_above=1)
MODEL = "gemma-4-26b-a4b-it"


def cite(id_="N-1", campo="descripcion", pasaje="limitará a 32 los tránsitos diarios") -> dict:
    return {"id_evidencia": id_, "campo": campo, "pasaje": pasaje}


def model_answer(**overrides) -> dict:
    base = {
        "estado": "respondida",
        "respuesta": "El Canal limitará a 32 los tránsitos diarios.",
        "citas": [cite()],
        "motivo_abstencion": None,
        "faltante": None,
        "versiones": [],
    }
    return base | overrides


def ask(llm, query="¿Cuántos tránsitos diarios limitará el Canal?", gate=GATE, retriever=RETRIEVER):
    return answer_query("Q-1", query, retriever, gate, EVIDENCES, llm, MODEL)


def test_an_answer_grounded_in_literal_citations_is_returned():
    llm = FakeLLM([model_answer()])
    answer = ask(llm)
    assert (answer.id_consulta, answer.estado) == ("Q-1", "respondida")
    assert answer.respuesta == "El Canal limitará a 32 los tránsitos diarios."
    assert answer.citas[0].pasaje == "limitará a 32 los tránsitos diarios"


def test_the_model_is_called_once_with_the_retrieved_sources_and_a_strict_schema():
    llm = FakeLLM([model_answer()])
    ask(llm)
    assert llm.n_calls == 1
    call = llm.calls[0]
    assert (call["model"], call["purpose"]) == (MODEL, "consulta")
    assert "N-1" in call["evidence_ids"]
    schema = call["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["citas"]["items"]["properties"]["id_evidencia"]["enum"][0] == "N-1"
    assert "<consulta>¿Cuántos tránsitos diarios limitará el Canal?</consulta>" in call["messages"][1]["content"]


def test_only_the_top_eight_hits_are_requested():
    asked = []

    class Spy:
        def search(self, query, k):
            asked.append(k)
            return [("N-1", 3.0)]

    ask(FakeLLM([model_answer()]), retriever=Spy())
    assert asked == [8]


def test_the_gate_abstains_without_calling_the_model():
    llm = FakeLLM([model_answer()])
    answer = ask(llm, query="¿Cuál será el PIB de Panamá en 2027?", gate=RetrievalGate(min_top_score=50, min_hits_above=1))
    assert answer.estado == "abstencion"
    assert answer.motivo_abstencion and answer.faltante
    assert llm.n_calls == 0


def test_a_query_with_no_retrieved_source_abstains_without_calling_the_model():
    llm = FakeLLM([model_answer()])
    answer = ask(llm, query="zzz qqq")
    assert answer.estado == "abstencion" and llm.n_calls == 0


def test_a_citation_that_is_not_literal_is_dropped_and_if_none_remain_the_answer_abstains():
    llm = FakeLLM([model_answer(citas=[cite(pasaje="el Canal cerrará por completo el lago Gatún")])])
    answer = ask(llm)
    assert answer.estado == "abstencion"
    assert answer.motivo_abstencion == UNVERIFIABLE_REASON
    assert answer.respuesta is None and answer.citas == ()


def test_invalid_citations_are_dropped_but_the_valid_ones_stay():
    llm = FakeLLM([model_answer(citas=[cite(), cite(pasaje="inventado de punta a punta del campo"), cite(id_="N-404")])])
    answer = ask(llm)
    assert answer.estado == "respondida"
    assert [c.id_evidencia for c in answer.citas] == ["N-1"]


def test_a_citation_that_differs_only_in_case_and_accents_is_repaired():
    llm = FakeLLM([model_answer(citas=[cite(pasaje="LIMITARA A 32 LOS TRANSITOS DIARIOS")])])
    answer = ask(llm)
    assert answer.citas[0].pasaje == "limitará a 32 los tránsitos diarios"


def test_an_answer_with_a_figure_the_sources_do_not_support_abstains():
    llm = FakeLLM([model_answer(respuesta="El Canal limitará a 40 los tránsitos diarios.")])
    answer = ask(llm)
    assert (answer.estado, answer.motivo_abstencion) == ("abstencion", UNVERIFIABLE_REASON)


def test_a_contradiction_needs_two_distinct_values_from_distinct_evidences():
    versions = [
        {"valor": "1,1 %", "alcance": "analistas citados por TVN", "id_evidencia": "N-2"},
        {"valor": "2,3 %", "alcance": "informe privado", "id_evidencia": "N-3"},
    ]
    llm = FakeLLM([model_answer(estado="contradiccion", respuesta=None, citas=[], versiones=versions)])
    answer = ask(llm, query="¿Cuál es la inflación de septiembre?")
    assert answer.estado == "contradiccion"
    assert [(v.valor, v.id_evidencia) for v in answer.versiones] == [("1,1 %", "N-2"), ("2,3 %", "N-3")]


@pytest.mark.parametrize(
    "versions",
    [
        [{"valor": "1,1 %", "alcance": "a", "id_evidencia": "N-2"}, {"valor": "1,1 %", "alcance": "b", "id_evidencia": "N-3"}],
        [{"valor": "1,1 %", "alcance": "a", "id_evidencia": "N-2"}, {"valor": "2,3 %", "alcance": "b", "id_evidencia": "N-2"}],
        [{"valor": "1,1 %", "alcance": "a", "id_evidencia": "N-2"}],
        [{"valor": "1,1 %", "alcance": "a", "id_evidencia": "N-2"}, {"valor": "2,3 %", "alcance": "b", "id_evidencia": "N-404"}],
    ],
)
def test_a_false_contradiction_falls_back_to_the_answer_when_its_citations_verify(versions):
    answer = ask(FakeLLM([model_answer(estado="contradiccion", versiones=versions)]))
    assert answer.estado == "respondida"
    assert answer.citas


def test_a_false_contradiction_without_verifiable_citations_abstains():
    versions = [{"valor": "1,1 %", "alcance": "a", "id_evidencia": "N-2"}]
    llm = FakeLLM([model_answer(estado="contradiccion", citas=[cite(pasaje="no existe en la fuente de ninguna forma")], versiones=versions)])
    assert ask(llm).estado == "abstencion"


@pytest.mark.parametrize(
    "failure",
    ["esto no es json", {"estado": "respondida"}, [1, 2], {"estado": "quizas"}, LLMError("sin respuesta")],
)
def test_a_malformed_model_answer_becomes_an_abstention(failure):
    answer = ask(FakeLLM([failure]))
    assert (answer.estado, answer.motivo_abstencion) == ("abstencion", INVALID_ANSWER_REASON)
    assert answer.faltante


def test_an_answer_with_no_citations_at_all_abstains():
    answer = ask(FakeLLM([model_answer(citas=[])]))
    assert answer.estado == "abstencion"


def test_when_the_model_abstains_its_reason_is_kept():
    llm = FakeLLM([model_answer(estado="abstencion", respuesta=None, citas=[], motivo_abstencion="No hay cifra.", faltante="La cifra oficial.")])
    answer = ask(llm)
    assert (answer.motivo_abstencion, answer.faltante) == ("No hay cifra.", "La cifra oficial.")


def test_a_model_abstention_without_a_reason_gets_a_default():
    answer = ask(FakeLLM([model_answer(estado="abstencion", respuesta=None, citas=[])]))
    assert answer.estado == "abstencion" and answer.motivo_abstencion and answer.faltante


def test_official_answers_keep_their_period():
    indicator_cite = cite("WB-PAN-X-2024", "valor", "44,36")
    llm = FakeLLM([model_answer(respuesta="Fueron 44,36 % del PIB en 2024.", citas=[indicator_cite])])
    answer = ask(llm, query="¿Cuánto representaron las exportaciones en 2024?")
    assert answer.estado == "respondida"
