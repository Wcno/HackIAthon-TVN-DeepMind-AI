import pytest


@pytest.mark.parametrize("structured", [False, True])
def test_qualitative_contradictions_require_actual_source_support(structured):
    evidence = by_id(news("N-1", titulo="Hospital sigue abierto"), news("N-2", titulo="Hospital sigue abierto"))
    class Hits:
        def search(self, query, k):
            return [("N-1", 1.0), ("N-2", .9)][:k]
    raw = model_answer(estado="contradiccion", respuesta=None, citas=[], afirmaciones=[], versiones=[
        {"valor": "cerrado definitivamente", "alcance": "anuncio", "id_evidencia": "N-1"},
        {"valor": "destruido", "alcance": "anuncio", "id_evidencia": "N-2"}])
    answer = answer_query("Q-1", "Hospital", Hits(), CosineGate(Hits(), min_cosine=.5),
                          evidence, FakeLLM([raw]), MODEL, structured=structured)
    assert answer.estado == "abstencion"


@pytest.mark.parametrize("structured", [False, True])
def test_contradictions_cannot_change_the_location_or_scope_of_supported_values(structured):
    evidence = by_id(news("N-1", titulo="Hospital abierto en David"), news("N-2", titulo="Hospital cerrado en David"))
    class Hits:
        def search(self, query, k):
            return [("N-1", 1.0), ("N-2", .9)][:k]
    raw = model_answer(estado="contradiccion", respuesta=None, citas=[], afirmaciones=[], versiones=[
        {"valor": "abierto", "alcance": "en Bogotá", "id_evidencia": "N-1"},
        {"valor": "cerrado", "alcance": "en Bogotá", "id_evidencia": "N-2"}])
    answer = answer_query("Q-1", "Hospital", Hits(), CosineGate(Hits(), min_cosine=.5),
                          evidence, FakeLLM([raw]), MODEL, structured=structured)
    assert answer.estado == "abstencion"


@pytest.mark.parametrize("structured", [False, True])
@pytest.mark.parametrize("titles, values", [
    (["Hospital sigue abierto desde hace 3 meses", "Hospital sigue abierto desde hace 4 meses"],
     ["cerrado durante 3 meses", "destruido hace 4 meses"]),
    (["Hospital reporta 2 % (2,0 %) de ocupación", "Hospital reporta 2 % (2,0 %) de ocupación"],
     ["2 %", "2,0 %"]),
])
def test_mixed_qualitative_inventions_and_equivalent_numbers_are_not_contradictions(structured, titles, values):
    evidence = by_id(*(news(f"N-{i}", titulo=title) for i, title in enumerate(titles, 1)))
    class Hits:
        def search(self, query, k):
            return [("N-1", 1.0), ("N-2", .9)][:k]
    raw = model_answer(estado="contradiccion", respuesta=None, citas=[], afirmaciones=[], versiones=[
        {"valor": value, "alcance": "Hospital", "id_evidencia": f"N-{i}"} for i, value in enumerate(values, 1)])
    answer = answer_query("Q-1", "Hospital", Hits(), CosineGate(Hits(), min_cosine=.5),
                          evidence, FakeLLM([raw]), MODEL, structured=structured)
    assert answer.estado == "abstencion"

from generation_fakes import FakeLLM, LLMError, by_id, indicator, news
from whoami.generation.prompting import CosineGate
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
GATE = CosineGate(RETRIEVER, min_cosine=0.5)  # BM25 scores stand in for cosines
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
    answer = ask(llm, query="¿Cuál será el PIB de Panamá en 2027?", gate=CosineGate(RETRIEVER, min_cosine=50))
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
        {"valor": "1,1 %", "alcance": "inflación anual de 1,1 % en septiembre", "id_evidencia": "N-2"},
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
    answer = ask(FakeLLM([failure, failure]))
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


def test_a_contradiction_version_with_a_figure_its_record_lacks_is_dropped():
    from whoami.generation.query_box import _distinct_versions
    from whoami.schemas import Evidence

    def news(news_id: str, title: str) -> Evidence:
        return Evidence(id_evidencia=news_id, tipo="noticia", titulo=title, url="https://x.invalid", fecha=None, campos={"titulo": title})

    evidences = {"N-a": news("N-a", "Metro transportó 9 millones"), "N-b": news("N-b", "Metro transportó 11 millones")}
    raw = [
        {"valor": "9 millones", "alcance": "Metro transportó", "id_evidencia": "N-a"},
        {"valor": "15 millones", "alcance": "Metro transportó", "id_evidencia": "N-b"},
    ]
    assert [v.valor for v in _distinct_versions(raw, {"N-a", "N-b"}, evidences)] == ["9 millones"]


def test_the_answer_call_caps_its_output_so_a_degenerate_model_fails_fast():
    from whoami.generation.query_box import ANSWER_MAX_TOKENS

    llm = FakeLLM([model_answer()])
    ask(llm)
    assert llm.calls[0]["max_tokens"] == ANSWER_MAX_TOKENS


def test_two_verified_versions_make_a_contradiction_even_if_the_model_says_answered():
    from whoami.generation.query_box import _verified
    from whoami.schemas import Evidence

    def item(news_id: str, title: str) -> Evidence:
        return Evidence(id_evidencia=news_id, tipo="noticia", titulo=title, url="https://x.invalid", fecha=None, campos={"titulo": title})

    evidences = {"N-a": item("N-a", "Más de 80 denuncias"), "N-b": item("N-b", "Más de 70 denuncias")}
    data = {"estado": "respondida", "respuesta": "Hay dos cifras: 80 y 70.",
            "citas": [{"id_evidencia": "N-a", "campo": "titulo", "pasaje": "Más de 80 denuncias"}],
            "versiones": [{"valor": "más de 80", "alcance": "denuncias", "id_evidencia": "N-a"}, {"valor": "más de 70", "alcance": "denuncias", "id_evidencia": "N-b"}]}
    assert _verified(data, "¿Cuántas?", evidences, {"N-a", "N-b"})["estado"] == "contradiccion"
