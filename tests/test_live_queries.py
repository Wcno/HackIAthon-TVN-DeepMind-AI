"""G6: a question outside the precalculated set is answered live, through the query box and its verification."""

import json

import httpx
from fastapi.testclient import TestClient

from whoami.backend.app import create_app
from whoami.backend.settings import Settings

SOURCE = "N-2cf673d2b74a"
QUESTION = "¿A cuántos tránsitos diarios se limitará el Canal en octubre?"
GROUNDED = {"estado": "respondida", "respuesta": "La Autoridad del Canal limitará a 32 los tránsitos diarios.",
            "citas": [{"id_evidencia": SOURCE, "campo": "descripcion", "pasaje": "limitará a 32 los tránsitos diarios"}],
            "motivo_abstencion": None, "faltante": None, "versiones": []}
INVENTED = GROUNDED | {"respuesta": "La Autoridad del Canal limitará a 99 los tránsitos diarios."}


class Provider:
    def __init__(self, reply=None, status=200):
        self.reply, self.status, self.requests = reply, status, []

    def __call__(self, request):
        self.requests.append(json.loads(request.content))
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"message": "boom"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(self.reply)}}]})


def app_with(tmp_path, provider, *, offline=False):
    settings = Settings(database=tmp_path / "db.sqlite3", offline=offline, gemini_api_key="" if offline else "test-secret",
                        generation_attempts=1)
    return TestClient(create_app(settings, gemini_transport=httpx.MockTransport(provider)))


def test_an_unseen_question_is_answered_with_verified_citations(tmp_path):
    provider = Provider(GROUNDED)
    with app_with(tmp_path, provider) as client:
        response = client.get("/queries", params={"q": QUESTION})
    assert response.status_code == 200
    assert "Respuesta con evidencia" in response.text and "32 los tránsitos" in response.text
    assert f"/evidence/{SOURCE}" in response.text
    assert len(provider.requests) == 1


def test_the_same_question_again_is_served_from_the_cache(tmp_path):
    provider = Provider(GROUNDED)
    with app_with(tmp_path, provider) as client:
        client.get("/queries", params={"q": QUESTION})
        again = client.get("/queries", params={"q": QUESTION})
    assert again.status_code == 200 and "32 los tránsitos" in again.text
    assert len(provider.requests) == 1


def test_an_answer_with_an_invented_figure_becomes_an_abstention(tmp_path):
    with app_with(tmp_path, Provider(INVENTED)) as client:
        response = client.get("/queries", params={"q": QUESTION})
    assert response.status_code == 200
    assert "No hay evidencia suficiente para responder" in response.text and "99 los" not in response.text


def test_when_gemini_fails_the_message_echoes_the_question_and_offers_a_next_step(tmp_path):
    with app_with(tmp_path, Provider(status=500)) as client:
        response = client.get("/queries", params={"q": QUESTION})
    assert response.status_code == 503
    assert "Intenta de nuevo" not in response.text
    assert f"«{QUESTION}»" in response.text
    assert "consulta precalculada" in response.text and "/queries?q=" in response.text


def test_offline_only_precalculated_questions_are_answered_and_gemini_is_not_called(tmp_path):
    provider = Provider(GROUNDED)
    with app_with(tmp_path, provider, offline=True) as client:
        response = client.get("/queries", params={"q": QUESTION})
        empty = client.get("/queries")
    assert response.status_code == 200 and "No hay una respuesta precalculada" in response.text
    assert provider.requests == []
    assert "sin conexión" in empty.text.casefold() and "precalculadas" in empty.text


def test_precalculated_lookup_ignores_accents_case_and_inverted_marks(tmp_path):
    with app_with(tmp_path, Provider(), offline=True) as client:
        known = client.app.state.repository.records("answer")[0]["consulta"]
        sloppy = known.replace("¿", "").replace("?", "").lower().translate(str.maketrans("áéíóúñ", "aeioun"))
        response = client.get("/queries", params={"q": sloppy})
    assert response.status_code == 200 and "No hay una respuesta precalculada" not in response.text


def test_the_page_has_a_query_form_and_a_nav_entry(tmp_path):
    with app_with(tmp_path, Provider(), offline=True) as client:
        html = client.get("/queries").text
    assert '>Consultas</a>' in html and 'aria-current="page">Consultas' in html
    assert 'action="/queries"' in html and 'name="q"' in html
    assert "buscador de arriba" not in html


def test_an_over_long_question_gets_a_query_specific_message(tmp_path):
    with app_with(tmp_path, Provider(), offline=True) as client:
        response = client.get("/queries", params={"q": "a" * 2001})
    assert response.status_code == 422
    assert "2.000" in response.text and "decisión" not in response.text


def test_one_badge_per_distinct_source(tmp_path):
    reply = GROUNDED | {"citas": GROUNDED["citas"] * 3}
    with app_with(tmp_path, Provider(reply)) as client:
        html = client.get("/queries", params={"q": QUESTION}).text
    assert html.count('class="cite"') == 1


def test_a_live_abstention_reads_as_sentences_with_a_real_next_step(tmp_path):
    reply = {"estado": "abstencion", "respuesta": None, "citas": [], "versiones": [],
             "motivo_abstencion": "las fuentes no dan la cifra", "faltante": None}
    with app_with(tmp_path, Provider(reply)) as client:
        html = client.get("/queries", params={"q": QUESTION}).text
    assert "Las fuentes no dan la cifra." in html
    assert html.count(QUESTION) == 2  # the form value and the heading: the next step does not repeat the question
    assert "Agrega una fuente" in html


def test_without_embeddings_the_corpus_has_no_cosines():
    from whoami.backend.retrieval import CorpusRetriever

    assert CorpusRetriever({}, None).cosine_search("canal", 1) is None


ABSTAINED = {"estado": "abstencion", "respuesta": None, "citas": [], "motivo_abstencion": "La consulta es demasiado amplia.",
             "faltante": "Una pregunta concreta.", "versiones": []}


def test_a_keyword_search_lists_the_matching_stories_even_when_the_model_abstains(tmp_path):
    with app_with(tmp_path, Provider(ABSTAINED)) as client:
        response = client.get("/queries", params={"q": "tránsitos diarios"})
    assert response.status_code == 200
    assert "Noticias relacionadas" in response.text
    assert f"/evidence/{SOURCE}" in response.text


def test_an_off_topic_search_lists_nothing_and_never_calls_the_model(tmp_path):
    provider = Provider(GROUNDED)
    with app_with(tmp_path, provider) as client:
        response = client.get("/queries", params={"q": "receta de sancocho"})
    assert "Noticias relacionadas" not in response.text
    assert provider.requests == []


def test_offline_a_keyword_search_still_lists_the_matching_stories(tmp_path):
    with app_with(tmp_path, Provider(), offline=True) as client:
        response = client.get("/queries", params={"q": "tránsitos diarios"})
    assert "Noticias relacionadas" in response.text
    assert f"/evidence/{SOURCE}" in response.text
