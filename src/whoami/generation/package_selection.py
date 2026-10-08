"""Editorial selection with mechanically bound factual prose.

The model chooses emphasis/order and investigation goals. It cannot supply
new factual sentences: code renders the accepted claims with their type and
attribution. Historical packages remain readable without claiming this proof.
"""

from collections.abc import Sequence

from whoami.contracts import HEADLINE_ONLY_LEGEND, TEXT_SCOPE_HEADLINE
from whoami.generation.prompting import leaks_canary
from whoami.schemas import Claim, EditorialPackage

FOCUSES = {
    "verificacion": "Contrastar el alcance de lo reportado y sus fuentes.",
    "impacto": "Investigar las consecuencias de lo reportado sin asumir causalidades.",
    "seguimiento": "Buscar actualizaciones y versiones que requieran contraste.",
}
QUESTIONS = {
    "fuentes": "¿Qué respaldan directamente las fuentes citadas?",
    "vacios": "¿Qué información falta por confirmar?",
    "actualizaciones": "¿Hay versiones o actualizaciones que deban contrastarse?",
    "periodo": "¿A qué período y ámbito corresponden los datos?",
    "impacto": "¿Qué consecuencias requieren investigación adicional?",
}
FACT_FIELDS = ("titulo", "brief", "guion", "copy_digital")


def render_claim(claim: Claim) -> str:
    if claim.tipo == "declaracion":
        return f"Declaración atribuida a {claim.atribuida_a}: {claim.texto}"
    if claim.tipo == "inferencia":
        return f"Inferencia por verificar: {claim.texto}"
    if claim.tipo == "hipotesis":
        return f"Hipótesis por verificar: {claim.texto}"
    return claim.texto


def selection_fields(selection: dict, claims: Sequence[Claim]) -> dict:
    expected = {*FACT_FIELDS, "enfoque", "preguntas"}
    if set(selection) != expected:
        raise ValueError("Editorial output must select claims, not introduce free factual prose")
    indexed = {claim.id_afirmacion: claim for claim in claims}
    fields = {}
    used = []
    for field in FACT_FIELDS:
        ids = selection[field]
        if (not isinstance(ids, (list, tuple)) or not ids or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids)
                or any(identity not in indexed for identity in ids) or (field == "titulo" and len(ids) != 1)):
            raise ValueError(f"Invalid accepted claim selection for {field}")
        fields[field] = " ".join(render_claim(indexed[identity]) for identity in ids)
        used.extend(ids)
    focus = selection["enfoque"]
    if isinstance(focus, (list, tuple)) and len(focus) == 1:
        focus = focus[0]
    questions = selection["preguntas"]
    if (not isinstance(focus, str) or focus not in FOCUSES or not isinstance(questions, (list, tuple))
            or any(not isinstance(q, str) for q in questions) or len(questions) != 3 or len(set(questions)) != 3):
        raise ValueError("Choose an editorial focus and three distinct investigation questions")
    if any(question not in QUESTIONS for question in questions):
        raise ValueError("Unknown investigation question")
    fields.update(enfoque_interes_publico=FOCUSES[focus], preguntas=tuple(QUESTIONS[q] for q in questions),
                  fuentes_y_verificaciones=tuple(f"Contrastar con sus fuentes citadas: {render_claim(indexed[i])}" for i in dict.fromkeys(used)))
    if any(leaks_canary(str(value)) for value in fields.values()):
        raise ValueError("Internal canary cannot enter the editorial package")
    return fields


def compose_package(selection: dict, claims: Sequence[Claim], scope: str) -> EditorialPackage:
    fields = selection_fields(selection, claims)
    proof = {field: tuple(selection[field]) for field in FACT_FIELDS}
    proof.update(enfoque=(selection["enfoque"],), preguntas=tuple(selection["preguntas"]))
    return EditorialPackage(**fields, respaldo=proof, leyenda=HEADLINE_ONLY_LEGEND if scope == TEXT_SCOPE_HEADLINE else None)


def verify_package(package: EditorialPackage, claims: Sequence[Claim]) -> None:
    if package.respaldo is None:
        return  # Legacy archives have no compositional proof, not a new-generation path.
    expected = selection_fields(package.respaldo, claims)
    if any(getattr(package, field) != value for field, value in expected.items()):
        raise ValueError("Editorial package text differs from its accepted claim references")
