"""Frozen, blind human review of retrieval and event-pair candidates.

This development experiment never changes the production model or reads G7's reserved set.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import secrets
import sqlite3
from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, select_autoescape
from whoami.backend.panama_time import panama_time


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def build_snapshot(rows: list[dict], queries: list[dict], candidates: dict, pairs: list[dict]) -> dict:
    """Freeze a union-of-top-five pool; resolve historical event pairs by IDs, never row offsets."""
    documents = {row["id_noticia"]: row for row in rows}
    query_ids = {query["qid"] for query in queries}
    pair_ids = {pair["id"] for pair in pairs}
    if len(documents) != len(rows) or len(query_ids) != len(queries) or len(pair_ids) != len(pairs):
        raise ValueError("Duplicate document, query or pair IDs")
    if not candidates or not queries:
        raise ValueError("Queries and candidates are required")
    items = []
    for candidate in candidates.values():
        if set(candidate["rankings"]) != query_ids:
            raise ValueError("Every candidate must rank the same queries")
        if candidate.get("pair_predictions") is not None and set(candidate["pair_predictions"]) != pair_ids:
            raise ValueError("Every grouping candidate must predict the same pairs")
        for ranking in candidate["rankings"].values():
            if len(ranking) > 5 or len(set(ranking)) != len(ranking) or not set(ranking) <= documents.keys():
                raise ValueError("Unknown, repeated or excessive document IDs in ranking")
    for query in queries:
        pool = set().union(*(set(c["rankings"][query["qid"]]) for c in candidates.values()))
        for document in sorted(pool):
            items.append({"id": f"R:{query['qid']}:{document}", "kind": "retrieval",
                          "query": query["qid"], "text": query["consulta"], "documents": [document]})
    for pair in pairs:
        if pair["id_a"] == pair["id_b"] or not {pair["id_a"], pair["id_b"]} <= documents.keys():
            raise ValueError("Unknown or identical document IDs in pair")
        items.append({"id": pair["id"], "kind": "pair", "documents": [pair["id_a"], pair["id_b"]]})
    # A reproducible blind order; no model names, ranks or previous machine labels in the review UI.
    items.sort(key=lambda item: fingerprint(item["id"]))
    used = set().union(*(set(item["documents"]) for item in items)) if items else set()
    snapshot = {"version": 1, "documents": {key: documents[key] for key in sorted(used)},
                "queries": queries, "candidates": candidates, "items": items,
                "scope": "public development; pooled top5; fixed grouping without LLM overrides"}
    snapshot["fingerprint"] = fingerprint(snapshot)
    return snapshot


class ReviewStore:
    """Labels and reviewer identity are durable and bound to exactly one frozen comparison."""

    def __init__(self, database: Path, snapshot: dict):
        self.database = database
        self.snapshot = snapshot
        self.items = {item["id"]: item for item in snapshot["items"]}
        database.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS identity (fingerprint TEXT PRIMARY KEY)")
            identity = connection.execute("SELECT fingerprint FROM identity").fetchone()
            if identity and identity[0] != snapshot["fingerprint"]:
                raise ValueError("Review database belongs to a different snapshot")
            connection.execute("INSERT OR IGNORE INTO identity VALUES (?)", (snapshot["fingerprint"],))
            connection.execute("CREATE TABLE IF NOT EXISTS labels (item TEXT PRIMARY KEY, grade TEXT NOT NULL, "
                               "actor TEXT NOT NULL, timestamp TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS history (item TEXT, grade TEXT, actor TEXT, timestamp TEXT)")

    def connect(self):
        return sqlite3.connect(self.database, timeout=10)

    def save(self, item: str, grade: str, actor: str) -> None:
        if item not in self.items:
            raise ValueError("Unknown review item")
        allowed = {"0", "1", "2", "unknown"} if self.items[item]["kind"] == "retrieval" else {
            "same_event", "ongoing_story", "different_event", "unknown"}
        if grade not in allowed or not actor.strip() or len(actor) > 120:
            raise ValueError("A valid grade and named human reviewer are required")
        values = (item, grade, actor.strip(), datetime.now(UTC).isoformat())
        with self.connect() as connection:
            connection.execute("INSERT INTO labels VALUES (?, ?, ?, ?) ON CONFLICT(item) DO UPDATE SET "
                               "grade=excluded.grade, actor=excluded.actor, timestamp=excluded.timestamp", values)
            connection.execute("INSERT INTO history VALUES (?, ?, ?, ?)", values)

    def labels(self) -> dict:
        with self.connect() as connection:
            return {row[0]: {"grade": row[1], "actor": row[2], "timestamp": row[3]}
                    for row in connection.execute("SELECT item, grade, actor, timestamp FROM labels")}


def score(snapshot: dict, store: ReviewStore) -> dict:
    """Only fully judged query pools count. Recall's denominator is ALL relevant pooled documents."""
    if snapshot["fingerprint"] != store.snapshot["fingerprint"]:
        raise ValueError("Labels belong to a different snapshot")
    return score_labels(snapshot, store.labels(), reviewer_kind="human")


def score_labels(snapshot: dict, labels: dict, *, reviewer_kind: str) -> dict:
    """Same metrics for both origins; keep the provenance and completion states explicit."""
    if reviewer_kind not in {"human", "agent"}:
        raise ValueError("Reviewer kind must be human or agent")
    usable = {key: value["grade"] for key, value in labels.items() if value["grade"] != "unknown"}
    retrieval, grouping = {}, {}
    for name, candidate in snapshot["candidates"].items():
        results = []
        for query in snapshot["queries"]:
            items = [item for item in snapshot["items"] if item.get("query") == query["qid"]]
            if not items or any(item["id"] not in usable for item in items):
                continue
            grades = {item["documents"][0]: int(usable[item["id"]]) for item in items}
            ranked = candidate["rankings"][query["qid"]]
            relevant = sum(value > 0 for value in grades.values())
            dcg = sum((2 ** grades[key] - 1) / math.log2(position + 2) for position, key in enumerate(ranked))
            ideal = sum((2 ** grade - 1) / math.log2(position + 2)
                        for position, grade in enumerate(sorted(grades.values(), reverse=True)[:5]))
            results.append({"precision_at_5": sum(grades[key] > 0 for key in ranked) / 5,
                            "pooled_recall_at_5": sum(grades[key] > 0 for key in ranked) / relevant if relevant else None,
                            "pooled_ndcg_at_5": dcg / ideal if ideal else None})
        retrieval[name] = {"eligible_queries": len(results)}
        for metric in ("precision_at_5", "pooled_recall_at_5", "pooled_ndcg_at_5"):
            values = [result[metric] for result in results if result[metric] is not None]
            retrieval[name][metric] = sum(values) / len(values) if values else None
            retrieval[name][metric + "_queries"] = len(values)
        predictions = candidate.get("pair_predictions")
        if predictions is None:
            grouping[name] = {"status": "not_applicable"}  # BM25 retrieves; it is not the deployed event grouper.
            continue
        tp = fp = fn = tn = 0
        for item, predicted in predictions.items():
            if item not in usable:
                continue
            actual = usable[item] == "same_event"
            tp += bool(predicted and actual)
            fp += bool(predicted and not actual)
            fn += bool(not predicted and actual)
            tn += bool(not predicted and not actual)
        denominator = 2 * tp + fp + fn
        grouping[name] = {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "reviewed_pairs": tp + fp + fn + tn,
                          "f1": 2 * tp / denominator if denominator else None}
    metrics_complete = len(usable) == len(snapshot["items"])
    complete = metrics_complete if reviewer_kind == "human" else len(labels) == len(snapshot["items"])
    return {"snapshot": snapshot["fingerprint"], "reviewer_kind": reviewer_kind,
            "status": f"{reviewer_kind}_review_complete" if complete else f"awaiting_{reviewer_kind}_review",
            "metrics_complete": metrics_complete, "unknown": len(labels) - len(usable),
            "decision": "keep_q4", "reviewed": len(usable), "submitted": len(labels), "total": len(snapshot["items"]),
            "retrieval": retrieval, "grouping": grouping,
            "limitations": "Pooled development relevance, not full-corpus recall; sampled pairs, not all events. "
                            "No automatic promotion. Compare quality first, then runtime and memory."}


def score_agent_reviews(snapshot: dict, reviews: list[dict]) -> dict:
    """Score agent judgments without opening, importing or changing any human review database."""
    items = {item["id"]: item for item in snapshot["items"]}
    labels = {}
    for review in reviews:
        if review.get("snapshot") != snapshot["fingerprint"] or review.get("reviewer_kind") != "agent":
            raise ValueError("Agent judgments require matching snapshot and explicit agent origin")
        item = review.get("item")
        if item not in items or item in labels:
            raise ValueError("Unknown or repeated agent review item")
        grades = {"0", "1", "2", "unknown"} if items[item]["kind"] == "retrieval" else {
            "same_event", "ongoing_story", "different_event", "unknown"}
        if (review.get("grade") not in grades or not isinstance(review.get("actor"), str)
                or not review["actor"].strip() or not isinstance(review.get("reason"), str) or not review["reason"].strip()):
            raise ValueError("Each agent judgment requires a valid grade, actor and reason")
        labels[item] = review
    result = score_labels(snapshot, labels, reviewer_kind="agent")
    result["judgments_fingerprint"] = fingerprint(reviews)
    result["reviewers"] = sorted({review["actor"] for review in reviews})
    result["limitations"] += " AI agent judgments are not independent human ground truth."
    return result


_REVIEW_ENV = Environment(autoescape=select_autoescape(default=True))


def source_url(value: str) -> str:
    try:
        return value if urlsplit(value).scheme in {"https", "http"} else "#"
    except ValueError:
        return "#"


_REVIEW_ENV.filters["source_url"] = source_url
_REVIEW_ENV.filters["panama_time"] = panama_time
_REVIEW_PAGE = _REVIEW_ENV.from_string('''
<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Evaluación humana de búsqueda y eventos</title><style>
body{font:18px/1.5 system-ui;max-width:850px;margin:32px auto;padding:0 20px;background:#f6f7f9;color:#14212c}
article{background:white;padding:20px;margin:16px 0;border:1px solid #d8dde3;border-radius:12px}
label{display:block;margin:12px 0}input,select,button{font:inherit;padding:10px;max-width:100%}
button{background:#173e67;color:white;border:0;border-radius:6px}a{color:#173e67}small{color:#45576a}
</style><h1>{{ 'Evaluación de modelos' if agent_report else 'Revisión humana' }}</h1>
{% if agent_report %}<p><strong>Evaluación del agente {{ 'completada' if agent_report.status == 'agent_review_complete' else 'en curso' }}: {{ agent_report.submitted }} / {{ total }}.</strong>
<a href="/agent-results">Ver comparación de modelos</a>. {{ agent_report.unknown }} decisión(es) indeterminada(s).</p>
<p>Son juicios de IA. La revisión humana es opcional.</p><details><summary>Revisión humana opcional</summary>{% endif %}
<p>{{ submitted }} / {{ total }} decisiones guardadas. Los candidatos están ocultos.</p>
{% if item %}<h2>{% if item.kind == 'retrieval' %}Consulta: {{ item.text }}{% else %}¿Informan del mismo hecho?{% endif %}</h2>
{% for document in documents %}<article><h3>{{ document.titulo }}</h3><small>{{ document.medio }} · {{ document.fecha_publicacion | panama_time }} (Panamá)</small>
<p>{{ document.descripcion }}</p><a href="{{ document.url | source_url }}" target="_blank" rel="noopener noreferrer">Leer fuente</a></article>{% endfor %}
<form method="post" action="/label"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="item" value="{{ item.id }}">
<label>Responsable <input name="actor" value="{{ actor }}" maxlength="120" required autocomplete="name"></label>
<label>Decisión <select name="grade" required><option value="">Elige…</option>
{% if item.kind == 'retrieval' %}<option value="2">2 · Responde directamente</option><option value="1">1 · Aporta contexto útil</option><option value="0">0 · No es pertinente</option>
{% else %}<option value="same_event">Mismo suceso, anuncio o decisión</option><option value="ongoing_story">Misma historia, distinto paso o fecha</option><option value="different_event">Hechos diferentes</option>{% endif %}
<option value="unknown">No puedo determinarlo</option></select></label><button>Guardar y continuar</button></form>
<p>No basta compartir un tema para ser el mismo hecho. La comparación no cambia el modelo de la app.</p>
{% else %}<p>Guardaste todas las decisiones. Las respuestas «no puedo determinarlo» siguen pendientes para las métricas.</p>{% endif %}
{% if agent_report %}</details>{% endif %}
<details><summary>Revisar una decisión</summary>{% for previous in items %}<p><a href="/?item={{ previous.id | urlencode }}">{{ loop.index }} · {{ previous.kind }}</a></p>{% endfor %}</details></html>
''')


def create_review_app(snapshot: dict, database: Path, *, agent_report: dict | None = None) -> FastAPI:
    """Local-only review UI, blind to candidate identities, with CSRF protection and durable labels."""
    store = ReviewStore(database, snapshot)
    csrf = secrets.token_urlsafe(32)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    if agent_report and (agent_report.get("snapshot") != snapshot["fingerprint"] or agent_report.get("reviewer_kind") != "agent"):
        raise ValueError("Agent report requires matching snapshot and explicit agent origin")

    @app.get("/agent-results", response_class=HTMLResponse)
    def agent_results():
        if agent_report is None:
            raise HTTPException(404, "No agent assessment available")
        return _AGENT_PAGE.render(report=agent_report)

    @app.get("/", response_class=HTMLResponse)
    def review(item: str | None = None, actor: str = ""):
        labels = store.labels()
        if item and item not in store.items:
            raise HTTPException(404, "Unknown review item")
        current = store.items.get(item) if item else next((i for i in snapshot["items"] if i["id"] not in labels), None)
        return _REVIEW_PAGE.render(item=current, documents=[snapshot["documents"][key] for key in current["documents"]] if current else [],
                                   csrf=csrf, actor=actor, submitted=len(labels), total=len(snapshot["items"]), items=snapshot["items"],
                                   agent_report=agent_report)

    @app.post("/label")
    def label(item: str = Form(), grade: str = Form(), actor: str = Form(), csrf_value: str = Form("", alias="csrf")):
        if not secrets.compare_digest(csrf_value, csrf):
            raise HTTPException(403, "Invalid review form")
        try:
            store.save(item, grade, actor)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        from urllib.parse import urlencode
        return RedirectResponse("/?" + urlencode({"actor": actor.strip()}), status_code=303)

    return app


_AGENT_PAGE = _REVIEW_ENV.from_string('''<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Comparación evaluada por el agente</title>
<style>body{font:17px/1.5 system-ui;max-width:950px;margin:32px auto;padding:0 16px;color:#14212c}
table{border-collapse:collapse;width:100%;font-size:15px}td,th{padding:8px;border-bottom:1px solid #d8dde3;text-align:left}
.scroll{overflow-x:auto}a{color:#173e67}</style><h1>Comparación evaluada por el agente</h1>
<p>{{ report.submitted }} / {{ report.total }} decisiones evaluadas por Codex (IA); {{ report.unknown }} indeterminada(s).
No se presentan como revisión humana. Los modelos mantienen sus espacios de vectores separados.</p>
<div class="scroll"><table><thead><tr><th>Candidato</th><th>Precisión@5</th><th>nDCG@5 del pool</th><th>Consultas</th></tr></thead><tbody>
{% for name, metrics in report.retrieval.items() %}<tr><th>{{ name }}</th><td>{{ '%.3f' | format(metrics.precision_at_5) if metrics.precision_at_5 is not none else '—' }}</td>
<td>{{ '%.3f' | format(metrics.pooled_ndcg_at_5) if metrics.pooled_ndcg_at_5 is not none else '—' }}</td><td>{{ metrics.eligible_queries }}</td></tr>{% endfor %}</tbody></table></div>
<h2>Agrupación de hechos</h2>{% for name, metrics in report.grouping.items() %}{% if metrics.f1 is defined %}
<p>{{ name }}: F1 {{ '%.3f' | format(metrics.f1) if metrics.f1 is not none else '—' }}, {{ metrics.reviewed_pairs }} pares puntuables;
{{ metrics.fp }} falsos positivos y {{ metrics.fn }} falsos negativos.</p>{% endif %}{% endfor %}
<p>La decisión del modelo permanece en q4. Estas métricas son del conjunto de desarrollo y sus candidatos seleccionados;
no prueban calidad en todo el corpus ni equivalen a validación humana independiente. No hay promoción automática.</p>
<p><a href="/">Volver a revisión opcional</a></p></html>''')


def load_agent_reviews(directory: Path) -> list[dict]:
    return [json.loads(line) for line in (directory / "agent-judgments.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


def load_snapshot(directory: Path) -> dict:
    snapshot = json.loads((directory / "snapshot.json").read_text(encoding="utf-8"))
    identity = snapshot.pop("fingerprint")
    if fingerprint(snapshot) != identity:
        raise ValueError("Comparison snapshot changed after preparation")
    snapshot["fingerprint"] = identity
    return snapshot


def add_arguments(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest="comparison_command", required=True)
    prepare = commands.add_parser("prepare", help="local inference, pinned public development data")
    prepare.add_argument("--directory", type=Path, required=True)
    prepare.add_argument("--threads", type=int, default=4)
    review = commands.add_parser("review", help="serve blind human review on localhost")
    review.add_argument("--directory", type=Path, required=True)
    review.add_argument("--port", type=int, default=8766)
    report = commands.add_parser("score", help="score existing human decisions; no model promotion")
    report.add_argument("--directory", type=Path, required=True)
    agent = commands.add_parser("score-agent", help="score explicit agent judgments separately from human decisions")
    agent.add_argument("--directory", type=Path, required=True)


def main(args: argparse.Namespace) -> int:
    if args.comparison_command == "prepare":
        from whoami.comparison_prepare import prepare
        prepare(args.directory, args.threads)
    elif args.comparison_command == "review":
        import uvicorn
        snapshot = load_snapshot(args.directory)
        agent_report = score_agent_reviews(snapshot, load_agent_reviews(args.directory)) if (args.directory / "agent-judgments.jsonl").is_file() else None
        uvicorn.run(create_review_app(snapshot, args.directory / "human.sqlite3", agent_report=agent_report), host="127.0.0.1", port=args.port)
    elif args.comparison_command == "score-agent":
        snapshot = load_snapshot(args.directory)
        reviews = load_agent_reviews(args.directory)
        result = score_agent_reviews(snapshot, reviews)
        (args.directory / "agent-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        snapshot = load_snapshot(args.directory)
        result = score(snapshot, ReviewStore(args.directory / "human.sqlite3", snapshot))
        (args.directory / "human-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
