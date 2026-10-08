from generation_fakes import by_id, news
from whoami.generation.version_citations import enrich_version_citations, support_version
from whoami.schemas import Answer, Citation, ContradictionVersion, citation_errors


def test_version_references_explicit_literal_source_fields():
    evidence = by_id(news("N-1", titulo="El Canal tendrá 33 tránsitos diarios en 2026."))
    version = support_version(ContradictionVersion(valor="33", alcance="anuncio de 2026", id_evidencia="N-1"), evidence)
    assert version is not None and version.citas
    assert all(citation.campo and citation.pasaje for citation in version.citas)
    assert citation_errors(version.citas, evidence) == []


def test_invented_scope_figures_do_not_get_citation_credit():
    evidence = by_id(news("N-1", titulo="El Canal tendrá 33 tránsitos diarios en 2026."))
    version = ContradictionVersion(valor="33", alcance="anuncio de 2099", id_evidencia="N-1")
    assert support_version(version, evidence) is None


def test_a_qualitative_value_must_be_present_even_when_its_scope_year_exists():
    evidence = by_id(news("N-1", titulo="El Canal informa en 2026."))
    version = ContradictionVersion(valor="cierre definitivo", alcance="en 2026", id_evidencia="N-1")
    assert support_version(version, evidence) is None


def test_saved_versions_can_be_enriched_without_model_calls():
    evidence = by_id(news("N-1", titulo="El Canal tendrá 33 tránsitos diarios."),
                     news("N-2", titulo="El Canal tendrá 32 tránsitos diarios."))
    original = Answer(id_consulta="Q-1", consulta="¿Cuántos?", estado="contradiccion", versiones=(
        ContradictionVersion(valor="33", alcance="primera fuente", id_evidencia="N-1"),
        ContradictionVersion(valor="32", alcance="segunda fuente", id_evidencia="N-2")))
    enriched = enrich_version_citations(original, evidence)
    assert all(version.citas for version in enriched.versiones)
    assert citation_errors(enriched.citas, evidence) == []
    assert not original.citas


def test_version_coverage_requires_its_cited_passage_to_support_scope_figures():
    from whoami.evaluation.datasets import BenchmarkCase
    from whoami.evaluation.metrics import answer_metrics, score_answer

    evidence = by_id(news("N-1", titulo="33 tránsitos", descripcion="Anuncio para 2026."),
                     news("N-2", titulo="32 tránsitos", descripcion="Anuncio para 2026."))
    answer = Answer(id_consulta="Q-1", consulta="¿Cuántos?", estado="contradiccion", versiones=tuple(
        ContradictionVersion(valor=value, alcance="en 2026", id_evidencia=identity,
                             citas=(Citation(id_evidencia=identity, campo="titulo", pasaje=f"{value} tránsitos"),))
        for identity, value in (("N-1", "33"), ("N-2", "32"))))
    case = BenchmarkCase(id="Q-1", kind="contradiction", query="¿Cuántos?", expected_states=("contradiccion",))
    measured = answer_metrics([case], [score_answer(case, answer, evidence)])
    assert measured["contradiction_version_coverage"] == {"numerator": 0, "denominator": 2}
    assert measured["query_factual_claim_coverage"]["value"] is None
