import pytest

from whoami.pipeline.topics_keywords import METHOD, classify_keywords


def test_the_method_name():
    assert METHOD == "palabras_clave_v1"


@pytest.mark.parametrize(
    ("text", "topic"),
    [
        ("Sube la inflación y el empleo en los bancos", "economia"),
        ("Un buque cruza el Canal por el puerto de Balboa", "logistica_canal"),
        ("Hotel espera más visitantes y viajeros en el destino", "turismo"),
        ("Hospital sin agua ni energía", "servicios_publicos"),
        ("Sismo y lluvia dejan sequía", "eventos_naturales"),
        ("Aprueban ley y decreto de regulación", "regulacion"),
    ],
)
def test_the_topic_with_most_keyword_hits_wins(text, topic):
    [(found, confidence, method)] = classify_keywords([text])

    assert found == topic
    assert 0 < confidence <= 1
    assert method == "palabras_clave_v1"


def test_confidence_is_hits_over_three_capped_at_one():
    [(_, one, _)] = classify_keywords(["Un sismo"])
    [(_, many, _)] = classify_keywords(["Sismo, terremoto, lluvia, sequía y huracán"])

    assert one == pytest.approx(1 / 3)
    assert many == 1.0


def test_no_keyword_means_no_topic_instead_of_defaulting_to_economy():
    assert classify_keywords(["Estrenan una película"]) == [("sin_tema", 0.0, "palabras_clave_v1")]


def test_ties_go_to_the_first_topic_in_the_contract_order():
    [(found, _, _)] = classify_keywords(["inflación y sismo"])

    assert found == "economia"


def test_it_classifies_a_batch_in_order():
    results = classify_keywords(["Sismo fuerte", "Nada que ver", "Nueva ley"])

    assert [topic for topic, _, _ in results] == ["eventos_naturales", "sin_tema", "regulacion"]
