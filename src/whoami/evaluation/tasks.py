"""G3 baselines and human claim-review accounting over aligned, frozen inputs."""

import json
from pathlib import Path

import numpy as np
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import StratifiedKFold

from whoami.evaluation.datasets import (
    PAIR_LABELS, TOPIC_LABELS, apply_human_labels, label_subject, read_records, sha256, subject_hash, unique_records, verify_review,
)
from whoami.evaluation.metrics import binary_counts, ratio
from whoami.pipeline.grouping import GROUP_WINDOW, group_agglomerative
from whoami.pipeline.provenance import near_identical
from whoami.pipeline.topics import TOPIC_ORDER, TopicModel
from whoami.pipeline.topics_keywords import classify_keywords
from whoami.schemas import Evidence, citation_errors, parse_utc
from whoami.embeddings import MODEL_NAME, MODEL_REVISION


def aligned_vectors(path: Path, evidence: dict[str, Evidence]) -> tuple[list[str], np.ndarray]:
    manifest = json.loads((path.parent / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("revision") != MODEL_REVISION or manifest.get("nombre") != MODEL_NAME:
        raise ValueError("Frozen vectors must use the same pinned embedding model as queries")
    if sha256(path) != manifest["sha256_vectores"]:
        raise ValueError("Frozen news vectors do not match their manifest")
    ids = manifest["ids"]
    vectors = np.load(path, allow_pickle=False)
    if len(set(ids)) != len(ids) or vectors.shape != (len(ids), manifest["dimensiones"]):
        raise ValueError("Vector dimensions/IDs do not match their manifest")
    news_ids = {item.id_evidencia for item in evidence.values() if item.tipo == "noticia" and not item.id_evidencia.startswith("N-syn")}
    if set(ids) != news_ids:
        raise ValueError("News vectors must cover exactly the frozen evidence corpus, not another CSV revision")
    if not np.isfinite(vectors).all():
        raise ValueError("Nonfinite news vectors")
    return ids, vectors


class SeededEmbedder:
    """Reuse verified corpus vectors for identical news text; encode only the remaining documents."""

    def __init__(self, embedder, ids, vectors, evidence):
        from whoami.generation.evidence_index import evidence_text

        self.embedder = embedder
        self.news = {evidence_text(evidence[identity]): np.asarray(vector, dtype=np.float32)
                     for identity, vector in zip(ids, vectors)}

    def embed_documents(self, texts):
        missing = [index for index, text in enumerate(texts) if text not in self.news]
        fresh = self.embedder.embed_documents([texts[index] for index in missing])
        by_index = dict(zip(missing, fresh))
        return np.asarray([self.news[text] if text in self.news else by_index[index] for index, text in enumerate(texts)], dtype=np.float32)

    def embed_queries(self, texts):
        return self.embedder.embed_queries(texts)


def topic_evaluation(ids, vectors, evidence, review_path: Path | None) -> tuple[dict, list[dict]]:
    gold, provenance = apply_human_labels(read_records(TOPIC_LABELS), "topic", review_path,
                                         lambda record: label_subject(record, "topic", evidence))
    position = {identity: index for index, identity in enumerate(ids)}
    missing = [row["id_noticia"] for row in gold if row["id_noticia"] not in position]
    if missing:
        raise ValueError(f"Topic evaluation cannot silently discard {len(missing)} missing subjects")
    for row in gold:
        if row["titulo"] != evidence[row["id_noticia"]].campos["titulo"]:
            raise ValueError(f"Topic label text changed: {row['id_noticia']}")
    x = vectors[[position[row["id_noticia"]] for row in gold]]
    truth = np.asarray([row["tema"] for row in gold])
    predicted = np.full(len(gold), "", dtype=object)
    folds = []
    for fold, (train, test) in enumerate(StratifiedKFold(n_splits=5, shuffle=True, random_state=7).split(x, truth)):
        model = TopicModel.fit(x[train], truth[train])
        predicted[test] = [item[0] for item in model.predict(x[test])]
        folds.append({"fold": fold, "train_ids": [gold[i]["id_noticia"] for i in train],
                      "test_ids": [gold[i]["id_noticia"] for i in test]})
    texts = [evidence[row["id_noticia"]].titulo + " " + evidence[row["id_noticia"]].campos.get("descripcion", "") for row in gold]
    baseline = [item[0] for item in classify_keywords(texts)]
    records = [{"id": row["id_noticia"], "gold": row["tema"], "keywords": first, "embeddings_cv": second}
               for row, first, second in zip(gold, baseline, predicted)]
    metrics = {}
    for name, predictions in (("keywords", baseline), ("embeddings_cv", predicted)):
        metrics[name] = {
            "n": len(gold), "macro_f1": float(f1_score(truth, predictions, labels=TOPIC_ORDER, average="macro", zero_division=0)),
            "correct": ratio([row["id_noticia"] for row, actual, pred in zip(gold, truth, predictions) if actual == pred],
                             [row["id_noticia"] for row in gold]),
            "per_class": classification_report(truth, predictions, labels=TOPIC_ORDER, output_dict=True, zero_division=0),
        }
    return {"labels": provenance, "methods": metrics, "folds": folds, "seed": 7,
            "limitation": "Exploratory 5-fold validation; embeddings model selection used these proposed labels in G3."}, records


def grouping_evaluation(ids, vectors, evidence, review_path: Path | None) -> tuple[dict, list[dict]]:
    gold, provenance = apply_human_labels(read_records(PAIR_LABELS), "pair", review_path,
                                         lambda record: label_subject(record, "pair", evidence))
    position = {identity: index for index, identity in enumerate(ids)}
    if any(row["id_a"] not in position or row["id_b"] not in position for row in gold):
        raise ValueError("Grouping evaluation cannot silently discard missing subjects")
    dates = [evidence[identity].fecha for identity in ids]
    if any(date is None for date in dates):
        raise ValueError("Grouping requires publication timestamps")
    groups = group_agglomerative(vectors, dates)
    membership = {ids[index]: group_id for group_id, group in enumerate(groups) for index in group}
    records = []
    for row in gold:
        first, second = row["id_a"], row["id_b"]
        baseline = abs(evidence[first].fecha - evidence[second].fecha) <= GROUP_WINDOW and near_identical(
            evidence[first].titulo, evidence[second].titulo,
        )
        records.append({"id": str(row["p"]), "first": first, "second": second, "gold": row["etiqueta"],
                        "keywords": baseline, "embeddings": membership[first] == membership[second]})
    truth = [record["gold"] == 2 for record in records]
    metrics = {name: binary_counts(truth, [bool(row[name]) for row in records]) for name in ("keywords", "embeddings")}
    for name in metrics:
        metrics[name]["failures"] = [row["id"] for row in records if (row["gold"] == 2) != row[name]]
    return {"labels": provenance, "methods": metrics, "groups": len(groups),
            "positive_definition": "label 2 = same event; labels 0 and 1 are negative, none are dropped",
            "configuration": "Production average linkage / 72 hours, without live LLM overrides"}, records


def claim_subject(case_id: str, claim: dict, evidence: dict[str, Evidence]) -> dict:
    return {
        "case_id": case_id, "claim": claim,
        "sources": {citation["id_evidencia"]: evidence[citation["id_evidencia"]].model_dump(mode="json")
                    for citation in claim["citas"] if citation["id_evidencia"] in evidence},
    }


def claim_evaluation(cases: list[dict], evidence: dict[str, Evidence], review_path: Path | None) -> tuple[dict, list[dict]]:
    from whoami.schemas import Citation

    decisions = unique_records(read_records(review_path), "subject_id") if review_path else {}
    packet, covered, reviewed, supported, errors = [], [], [], [], []
    seen_text = set()
    for case in cases:
        for claim in case["afirmaciones"]:
            identity = f"{case['id_caso']}/{claim['id_afirmacion']}"
            subject = claim_subject(case["id_caso"], claim, evidence)
            fingerprint = subject_hash(subject)
            item = {"subject_id": identity, "subject_hash": fingerprint, "subject": subject,
                    "reviewer": "", "reviewed_at": "", "verdict": "", "note": ""}
            packet.append(item)
            citations = [Citation.model_validate(value) for value in claim["citas"]]
            if citations and not citation_errors(citations, evidence):
                covered.append(identity)
            review = decisions.get(identity)
            if review is None:
                continue
            try:
                verify_review(review, fingerprint)
                if review["verdict"] not in ("supported", "unsupported", "unclear"):
                    raise ValueError("Claim verdict must be supported, unsupported or unclear")
                # Repeating the same statement cannot satisfy the 30-claim requirement.
                statement = subject_hash({"text": claim["texto"], "citations": claim["citas"]})
                if statement in seen_text:
                    raise ValueError("Duplicate statement in human review sample")
                seen_text.add(statement)
                reviewed.append(identity)
                if review["verdict"] == "supported":
                    supported.append(identity)
            except (ValueError, KeyError, TypeError) as error:
                errors.append({"id": identity, "reason": str(error)})
    all_ids = [item["subject_id"] for item in packet]
    if len(set(all_ids)) != len(all_ids):
        raise ValueError("Duplicate generated claim identity")
    return {
        "citation_coverage": ratio(covered, all_ids), "human_support": ratio(supported, reviewed),
        "reviewed_unique_claims": len(reviewed), "minimum_sample": 30,
        "meets_human_target": len(reviewed) >= 30 and len(supported) / len(reviewed) >= 0.9,
        "review_errors": errors, "unknown_review_ids": sorted(set(decisions) - set(all_ids)),
        "pending": [identity for identity in all_ids if identity not in reviewed],
    }, packet
