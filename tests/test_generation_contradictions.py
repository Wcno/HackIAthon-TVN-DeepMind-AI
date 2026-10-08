import pytest

from generation_fakes import FakeLLM, LLMError, by_id, group, member, news
from whoami.generation.contradictions import (
    LLMContradictionChecker,
    RuleBasedChecker,
    date_conflicts,
    numeric_conflicts,
)


def build(*articles, **members):
    """Group of members `N-1`, `N-2`... one per article text, with per-member overrides `m1={...}`."""
    evidences = by_id(*(news(f"N-{n}", titulo=text) for n, text in enumerate(articles, start=1)))
    group_members = [member(f"N-{n}", **members.get(f"m{n}", {"medio": f"Medio{n}"})) for n in range(1, len(articles) + 1)]
    return group(group_members), evidences


def test_different_percentages_for_the_same_metric_are_a_contradiction():
    g, evidences = build(
        "Analistas citan una inflación anual de 1,1 % en septiembre",
        "Un informe privado ubica la inflación anual en 2,3 % en septiembre",
    )
    [found] = numeric_conflicts(g, evidences)
    assert [(v.valor, v.id_evidencia) for v in found.versiones] == [("1,1 %", "N-1"), ("2,3 %", "N-2")]
    assert found.versiones[0].alcance == "Medio1, 5 de octubre de 2026"
    assert "inflación" in found.descripcion


def test_equal_values_are_not_a_contradiction():
    g, evidences = build("La inflación anual fue 2,3 % en septiembre", "Inflación de 2,3 % según el informe")
    assert numeric_conflicts(g, evidences) == ()


def test_different_metrics_with_the_same_unit_are_not_a_contradiction():
    g, evidences = build("La inflación anual fue 2,3 % en septiembre", "El desempleo subió a 7,5 % en septiembre")
    assert numeric_conflicts(g, evidences) == ()


def test_counts_of_the_same_thing_are_compared_by_their_unit():
    g, evidences = build(
        "El Canal limitará a 32 los tránsitos diarios",
        "La ACP reducirá a 36 tránsitos diarios el paso de buques",
    )
    [found] = numeric_conflicts(g, evidences)
    assert {v.valor for v in found.versiones} == {"32 tránsitos", "36 tránsitos"}


def test_days_months_and_years_are_not_figures():
    g, evidences = build("El Canal limitará los tránsitos desde el 12 de octubre de 2026", "El Canal limitará los tránsitos desde el 15 de octubre de 2025")
    assert numeric_conflicts(g, evidences) == ()


def test_the_same_provenance_on_the_same_date_is_one_voice_not_two():
    g, evidences = build(
        "La inflación anual fue 1,1 % en septiembre",
        "La inflación anual fue 2,3 % en septiembre",
        m1={"medio": "TVN", "procedencia": "EFE"},
        m2={"medio": "Telemetro", "procedencia": "EFE"},
    )
    assert numeric_conflicts(g, evidences) == ()


def test_the_same_provenance_at_different_dates_can_contradict_itself():
    g, evidences = build(
        "La inflación anual fue 1,1 % en septiembre",
        "La inflación anual fue 2,3 % en septiembre",
        m1={"medio": "TVN", "procedencia": "EFE", "fecha": "2026-10-05T14:00:00Z"},
        m2={"medio": "TVN", "procedencia": "EFE", "fecha": "2026-10-06T14:00:00Z"},
    )
    assert len(numeric_conflicts(g, evidences)) == 1


def test_members_without_evidence_are_skipped():
    g, evidences = build("La inflación anual fue 1,1 %", "La inflación anual fue 2,3 %")
    assert numeric_conflicts(g, {"N-1": evidences["N-1"]}) == ()


def test_a_different_date_for_the_same_event_is_a_contradiction():
    g, evidences = build(
        "El Canal limitará los tránsitos desde el 12 de octubre",
        "El Canal limitará los tránsitos a partir del 15 de octubre",
    )
    [found] = date_conflicts(g, evidences)
    assert [(v.valor, v.id_evidencia) for v in found.versiones] == [("12 de octubre", "N-1"), ("15 de octubre", "N-2")]
    assert "limit" in found.descripcion


def test_dates_of_different_events_are_not_a_contradiction():
    g, evidences = build("El IDAAN anunció el corte el 9 de octubre", "La alcaldía inaugurará la obra el 20 de octubre")
    assert date_conflicts(g, evidences) == ()


def test_the_same_date_is_not_a_contradiction():
    g, evidences = build("El IDAAN cortará el agua el 9 de octubre", "El IDAAN cortará el servicio el 9 de octubre")
    assert date_conflicts(g, evidences) == ()


def test_the_rule_based_checker_finds_both_kinds():
    g, evidences = build(
        "La inflación anual fue 1,1 % y el Canal limitará los tránsitos desde el 12 de octubre",
        "La inflación anual fue 2,3 % y el Canal limitará los tránsitos desde el 15 de octubre",
    )
    found = RuleBasedChecker().check(g, evidences)
    assert len(found) == 2
    assert found == numeric_conflicts(g, evidences) + date_conflicts(g, evidences)


PAIR = {"contradiccion": True, "descripcion": "Dos cifras distintas.", "valor_a": "1,1 %", "valor_b": "2,3 %"}


def test_the_llm_checker_turns_a_positive_answer_into_a_contradiction():
    g, evidences = build("Inflación de uno coma uno", "Inflación de dos coma tres")
    llm = FakeLLM([PAIR])
    [found] = LLMContradictionChecker(llm, "modelo").check(g, evidences)
    assert found.descripcion == "Dos cifras distintas."
    assert [(v.valor, v.id_evidencia) for v in found.versiones] == [("1,1 %", "N-1"), ("2,3 %", "N-2")]
    call = llm.calls[0]
    assert call["purpose"] == "contradiccion" and call["evidence_ids"] == ["N-1", "N-2"]
    assert call["response_format"]["json_schema"]["schema"]["required"] == ["contradiccion", "descripcion", "valor_a", "valor_b"]


def test_the_llm_checker_asks_once_per_eligible_pair():
    evidences = by_id(*(news(f"N-{n}", titulo="x") for n in (1, 2, 3)))
    g = group([member("N-1", "A"), member("N-2", "A", procedencia="A"), member("N-3", "B")])
    llm = FakeLLM(lambda call: {**PAIR, "contradiccion": False})
    assert LLMContradictionChecker(llm, "modelo").check(g, evidences) == ()
    assert llm.n_calls == 2  # the first two are the same voice on the same day
    same_voice = group([member("N-1", "A", procedencia="EFE"), member("N-2", "B", procedencia="EFE")])
    llm = FakeLLM(lambda call: PAIR)
    assert LLMContradictionChecker(llm, "modelo").check(same_voice, evidences) == ()
    assert llm.n_calls == 0


@pytest.mark.parametrize("failure", ["no es json", {"contradiccion": True}, LLMError("boom"), {**PAIR, "valor_a": " "}])
def test_the_llm_checker_ignores_unusable_answers(failure):
    g, evidences = build("uno", "dos")
    assert LLMContradictionChecker(FakeLLM([failure]), "modelo").check(g, evidences) == ()
