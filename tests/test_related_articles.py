"""G6: related-article suggestions need real topic overlap, so generic headline words never pad the list."""

from whoami.backend.assistant import DraftAssistant

CANAL_TITLE = "Canal de Panamá anuncia nueva fase del Programa de Asignación de Cupos a Largo Plazo en las esclusas Neopanamax"


def news(key, title, description=""):
    return {"id_evidencia": key, "tipo": "noticia", "titulo": title, "url": f"https://example.org/{key}", "fecha": "2026-09-28",
            "campos": {"descripcion": description} if description else {}}


class StubRepository:
    def __init__(self, items, own):
        self.items = items
        self.own = own

    def records(self, kind):
        return self.items if kind == "evidence" else []

    def record(self, kind, key):
        return {"miembros": [{"id_noticia": i, "medio": "Medio"} for i in self.own], "contexto": []}


CORPUS = [
    news("N-own1", CANAL_TITLE, "Cupos a largo plazo para las esclusas del Canal de Panamá"),
    news("N-own2", "Programa de cupos a largo plazo del Canal de Panamá", "Esclusas Neopanamax y Panamax"),
    news("N-canal1", "Canal de Panamá abre cupos para esclusas Neopanamax", "Tránsitos en las esclusas del Canal"),
    news("N-canal2", "ACP detalla el programa de cupos a largo plazo en el Canal de Panamá"),
    news("N-cepanim", "Cepanim anuncia nueva fase de atención para familiares"),
    news("N-trump", "Trump anuncia la ampliación de un programa de medicamentos"),
    news("N-musica", "Oasis anuncia una nueva gira con un programa de conciertos"),
]
CASE = {"titulo": CANAL_TITLE, "ids_fuente": ["N-own1", "N-own2"], "id_grupo": "G-1"}


def assistant():
    return DraftAssistant(StubRepository(CORPUS, ["N-own1", "N-own2"]))


def found(answer):
    return [article["id_evidencia"] for article in answer["articles"]]


def test_unrelated_stories_sharing_generic_words_are_not_suggested():
    answer = assistant().search(CASE, "Busca otras noticias sobre este tema")
    assert answer["kind"] == "articles"
    assert sorted(found(answer)) == ["N-canal1", "N-canal2"]


def test_case_sources_stay_excluded_and_fewer_than_four_is_fine():
    assert not {"N-own1", "N-own2"} & set(found(assistant().search(CASE, "Busca otras noticias sobre este tema")))


def test_no_related_story_gives_a_useful_empty_message():
    only_generic = DraftAssistant(StubRepository([*CORPUS[:2], *CORPUS[4:]], ["N-own1", "N-own2"]))
    answer = only_generic.search(CASE, "Busca otras noticias sobre este tema")
    assert answer["kind"] == "abstention"
    assert answer["missing"]


def test_semantic_scores_must_clear_the_case_floor_when_available():
    system = assistant()
    cosines = {"N-canal1": 0.5, "N-canal2": 0.3}
    system.index.cosine_search = lambda query, k: list(cosines.items())
    assert found(system.search(CASE, "Busca otras noticias sobre este tema")) == ["N-canal1"]


def test_a_short_explicit_question_needs_only_its_own_term():
    assert {"N-canal1", "N-canal2"} <= set(found(assistant().search(CASE, "Busca noticias sobre el Canal")))
