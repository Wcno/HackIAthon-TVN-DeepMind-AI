"""Pipeline core: news rows and vectors in, a validated `OutputSet` out (groups, evidence, no case files yet).

Classification and grouping are injected, so the experiments can replace them without touching the rest:
`classify(rows, vectors) -> [(topic, confidence, method)]` and `group(vectors, dates) -> [[row index, ...], ...]`.
"""

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from whoami import store
from whoami.contracts import MANIFEST_JSON, OUTPUTS, PROCESSED
from whoami.embeddings import MODEL_NAME
from whoami.pipeline.context import link_context
from whoami.pipeline.evidence import load_news_rows, load_official_evidence, news_evidence
from whoami.pipeline.grouping import GROUP_WINDOW, group_agglomerative, unit_vectors
from whoami.pipeline.provenance import merge_provenances, provenance
from whoami.pipeline.recirculation import apply_recirculations, group_recirculations, metadata_recirculation
from whoami.pipeline.scoring import evidence_state, score_group
from whoami.pipeline.text import rows_text
from whoami.pipeline.topics_keywords import classify_keywords
from whoami.schemas import Evidence, Group, Member, OutputSet, parse_utc, sort_inbox

Classifier = Callable[[Sequence[Mapping[str, str]], np.ndarray], list[tuple[str, float, str]]]
Grouper = Callable[[np.ndarray, Sequence[datetime]], list[list[int]]]
Configure = Callable[[Sequence[Mapping[str, str]], np.ndarray], tuple[Classifier, Grouper]]

SIMILARITY_THRESHOLD = 0.85  # cosine; only `group_by_similarity`, kept to compare against the default grouper
EMBEDDINGS_DIR = PROCESSED / "embeddings"


class PipelineInputError(Exception):
    """An input of the pipeline is missing or does not match the news; the message says what to fix."""


def group_by_similarity(
    vectors: np.ndarray,
    dates: Sequence[datetime],
    threshold: float = SIMILARITY_THRESHOLD,
    window: timedelta = GROUP_WINDOW,
) -> list[list[int]]:
    """Single-link: pairs above the threshold and inside the window are joined, most similar first."""
    unit = unit_vectors(np.asarray(vectors, dtype=float))
    similarity = unit @ unit.T
    hours = np.array([date.timestamp() / 3600 for date in dates])
    close = np.abs(hours[:, None] - hours[None, :]) <= window.total_seconds() / 3600
    first, second = np.nonzero(np.triu((similarity >= threshold) & close, k=1))
    parent = list(range(len(dates)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for pair in np.argsort(-similarity[first, second], kind="stable"):
        parent[find(first[pair])] = find(second[pair])
    members: dict[int, list[int]] = defaultdict(list)
    for index in range(len(dates)):
        members[find(index)].append(index)
    return sorted(members.values())


def classify_by_keywords(rows: Sequence[Mapping[str, str]], vectors: np.ndarray) -> list[tuple[str, float, str]]:
    return classify_keywords([rows_text([row]) for row in rows])


def _group_id(member_ids: Sequence[str]) -> str:
    return "G-" + hashlib.sha1(",".join(sorted(member_ids)).encode()).hexdigest()[:10]


def _vote(topics: Sequence[tuple[str, float, str]]) -> str:
    """Majority topic; a tie goes to the topic with the highest summed confidence."""
    votes: Counter[str] = Counter()
    confidence: defaultdict[str, float] = defaultdict(float)
    for topic, topic_confidence, _ in topics:
        votes[topic] += 1
        confidence[topic] += topic_confidence
    return max(votes, key=lambda topic: (votes[topic], confidence[topic]))


def _topic_method(topics: Sequence[tuple[str, float, str]], topic: str) -> str:
    """How the winning topic was assigned: `llm` when any member that voted for it came from the LLM."""
    methods = {method for voted, _, method in topics if voted == topic}
    return "llm" if "llm" in methods else min(methods)


def _member(row: Mapping[str, str]) -> Member:
    return Member(
        id_noticia=row["id_noticia"],
        titulo=row["titulo"],
        url=row["url"],
        medio=row["medio"],
        procedencia=provenance(dict(row)),
        fecha_publicacion=parse_utc(row["fecha_publicacion"]),
        alcance_texto=row["alcance_texto"],
        recirculada_en=None,
    )


def _members_of(rows: Sequence[Mapping[str, str]]) -> list[Member]:
    """Members with recirculation (metadata, then inside the group) and merged provenance applied."""
    members = [_member(row) for row in rows]
    members = apply_recirculations(
        members, [found for row in rows if (found := metadata_recirculation(dict(row))) is not None]
    )
    members = apply_recirculations(members, group_recirculations(members))
    return merge_provenances(members)


def build(
    rows: Sequence[Mapping[str, str]],
    vectors: np.ndarray,
    classify: Classifier,
    group: Grouper,
    fecha_corte: datetime,
    official: Mapping[str, Evidence] | None = None,
) -> OutputSet:
    """`official` defaults to every official record in `data/processed/`."""
    official = load_official_evidence() if official is None else official
    unit = unit_vectors(np.asarray(vectors, dtype=float))
    dates = [parse_utc(row["fecha_publicacion"]) for row in rows]
    topics = classify(rows, unit)

    drafts = []
    for indices in group(unit, dates):
        ordered = sorted(indices, key=lambda i: (dates[i], rows[i]["id_noticia"]))
        members = _members_of([rows[i] for i in ordered])
        centroid = unit_vectors(unit[ordered].mean(axis=0, keepdims=True))[0]
        central = ordered[int(np.argmax(unit[ordered] @ centroid))]
        drafts.append((ordered, members, centroid, rows[central]["titulo"]))

    earliest = [min(m.fecha_publicacion for m in members) for _, members, _, _ in drafts]
    centroids = np.array([centroid for _, _, centroid, _ in drafts]).reshape(len(drafts), -1)
    centroid_similarity = centroids @ centroids.T

    groups = []
    for position, (ordered, members, _, title) in enumerate(drafts):
        group_rows = [rows[i] for i in ordered]
        group_topics = [topics[i] for i in ordered]
        topic = _vote(group_topics)
        context, no_context_reason = link_context(rows_text(group_rows), earliest[position], topic, official)
        earlier = [other for other in range(len(drafts)) if earliest[other] < earliest[position]]
        max_similarity = max((float(centroid_similarity[position, other]) for other in earlier), default=0.0)
        groups.append(
            Group(
                id_grupo=_group_id([m.id_noticia for m in members]),
                titulo=title,
                tema=topic,
                miembros=tuple(members),
                puntaje=score_group(group_rows, members, topic, bool(context), max_similarity, fecha_corte, _topic_method(group_topics, topic)),
                estado_evidencia=evidence_state(group_rows, len({m.procedencia for m in members}), bool(context)),
                contexto=context,
                sin_contexto_motivo=no_context_reason,
                id_caso=None,
            )
        )

    evidences = {row["id_noticia"]: news_evidence(dict(row)) for row in rows} | dict(official)
    return OutputSet(grupos=tuple(sort_inbox(groups)), evidencias=evidences, fichas=(), consultas=(), revisiones=())


def default_vectors_path() -> Path:
    """The vectors of the corpus model (`whoami embed`); else the only `.npy` in `data/processed/embeddings/`."""
    preferred = EMBEDDINGS_DIR / f"{MODEL_NAME}.npy"
    if preferred.exists():
        return preferred
    found = sorted(EMBEDDINGS_DIR.glob("*.npy"))
    if len(found) != 1:
        raise PipelineInputError(
            f"se esperaba exactamente un archivo .npy en {EMBEDDINGS_DIR} y hay {len(found)}: indica uno con --vectors"
        )
    return found[0]


def load_vectors(path: Path, rows: Sequence[Mapping[str, str]]) -> np.ndarray:
    """Vectors saved with `np.save`, next to a `manifest.json` whose `ids` give their order."""
    if not path.exists():
        raise PipelineInputError(f"no existe {path}: los vectores se generan antes de correr el pipeline")
    manifest = path.parent / "manifest.json"
    if not manifest.exists():
        raise PipelineInputError(f"no existe {manifest}: debe listar los ids en el orden de los vectores")
    described = json.loads(manifest.read_text(encoding="utf-8"))
    ids = described["ids"]
    expected_hash = described.get("sha256_vectores")
    if expected_hash is not None and hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
        raise PipelineInputError(f"{path} no coincide con sha256_vectores de {manifest}: regenera los vectores con `whoami embed`")
    if ids != [row["id_noticia"] for row in rows]:
        raise PipelineInputError(f"los ids de {manifest} no coinciden con noticias.csv (mismo orden y mismas noticias)")
    vectors = np.load(path)
    if len(vectors) != len(ids):
        raise PipelineInputError(f"{path} tiene {len(vectors)} vectores y el manifiesto {len(ids)} ids")
    return vectors


def run(
    vectors_path: Path | None = None,
    data: Path = PROCESSED,
    outputs: Path = OUTPUTS,
    classify: Classifier = classify_by_keywords,
    group: Grouper = group_agglomerative,
    configure: Configure | None = None,
) -> OutputSet:
    """Reads the processed data, builds the groups and writes them where `store.load` reads them.

    `configure(rows, vectors) -> (classify, group)` builds both from the loaded data and replaces the two arguments."""
    rows = load_news_rows()
    vectors = load_vectors(vectors_path or default_vectors_path(), rows)
    fecha_corte = parse_utc(json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))["fecha_corte_UTC"])
    if configure is not None:
        classify, group = configure(rows, vectors)
    output = build(rows, vectors, classify, group, fecha_corte)
    store.write(output, data, outputs)
    return output
