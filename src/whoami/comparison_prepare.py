"""Isolated CPU runs for the public development comparison; no production artifacts are rewritten."""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

from whoami import embeddings
from whoami.contracts import DATA, PROCESSED
from whoami.generation.prompting import MIN_COSINE
from whoami.generation.retrieval import BM25Index, Document, EmbeddingIndex, hybrid_rrf
from whoami.model_comparison import build_snapshot, fingerprint
from whoami.pipeline.evidence import load_news_rows, news_evidence
from whoami.pipeline.grouping import group_agglomerative, DISTANCE_THRESHOLD
from whoami.pipeline.run import load_vectors

FP32_HASHES = {
    "onnx/model.onnx": "ea91fd315a7c152d427d231746f0f811a1ac93beaba656abfdf2b24e091265e4",
    "onnx/model.onnx_data": "ef835ae565d8695236652475903078e8ed794c7c35faf1164d78ec3238e8a88d",
    "tokenizer.json": "4dda02faaf32bc91031dc8c88457ac272b00c1016cc679757d1c441b248b9c47",
}
ROOT = DATA.parent
QUERIES = ROOT / "experiments/g3/datos/queries.jsonl"
PAIRS = ROOT / "experiments/g3/datos/pairs_gold.jsonl"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def public_inputs():
    rows = load_news_rows()
    ids = {row["id_noticia"] for row in rows}
    # Labels and historical positional indices are intentionally discarded, not imported as human truth.
    pairs = [{"id": f"P:{p['id_a']}:{p['id_b']}", "id_a": p["id_a"], "id_b": p["id_b"]}
             for p in read_lines(PAIRS) if p["id_a"] in ids and p["id_b"] in ids]
    unique = {pair["id"]: pair for pair in pairs}
    pairs = sorted(unique.values(), key=fingerprint)[:50]
    queries = read_lines(QUERIES)
    context = {"corpus": embeddings.corpus_fingerprint(rows), "full_rows": fingerprint(rows),
               "queries": digest(QUERIES), "pairs": fingerprint(pairs),
               "revision": embeddings.MODEL_REVISION, "storage_dtype": "float16", "query_dtype": "float32",
               "document_prefix": embeddings.DOCUMENT_PREFIX, "query_prefix": embeddings.QUERY_PREFIX,
               "max_tokens": embeddings.MAX_TOKENS, "pool": 20, "cosine_gate": MIN_COSINE,
               "group_distance": DISTANCE_THRESHOLD, "group_window_hours": 72,
               "production_vector_manifest": digest(PROCESSED / "embeddings/manifest.json")}
    return rows, queries, pairs, context


def validate_cached_report(report: dict, name: str, context: dict, expected_files: dict) -> None:
    provenance = report["provenance"]
    if report["context"] != context:
        raise ValueError("Candidate report has different corpus, queries, pairs or configuration")
    if (provenance["files"] != expected_files or provenance["model"] != name
            or provenance["revision"] != embeddings.MODEL_REVISION or provenance["repository"] != embeddings.MODEL_REPO):
        raise ValueError("Cached candidate model identity differs from pinned files")


def validate_vectors(vectors: np.ndarray, count: int) -> None:
    if vectors.shape != (count, embeddings.DIMENSIONS) or not np.isfinite(vectors).all():
        raise ValueError("Invalid candidate vector shape or values")
    if np.any(np.linalg.norm(vectors.astype(np.float32), axis=1) == 0):
        raise ValueError("Candidate contains zero vectors")


def peak_rss_mib() -> float:
    """Peak resident memory of this isolated run, including grouping and Python; not weights alone."""
    if sys.platform != "win32":
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak / (1024 ** 2 if sys.platform == "darwin" else 1024)
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (key, ctypes.c_size_t) for key in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                            "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    values = Counters()
    values.cb = ctypes.sizeof(values)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    function = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    function.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not function(kernel.GetCurrentProcess(), ctypes.byref(values), values.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return values.PeakWorkingSetSize / 1024 ** 2


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".part")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_candidate(name: str, directory: Path, threads: int) -> None:
    import onnxruntime

    rows, queries, pairs, context = public_inputs()
    context["threads"] = threads
    if name == "q4":
        model = embeddings.model_dir()
        manifest = json.loads((PROCESSED / "embeddings/manifest.json").read_text(encoding="utf-8"))
        required = {"modelo": embeddings.MODEL_REPO, "revision": embeddings.MODEL_REVISION,
                    "nombre": embeddings.MODEL_NAME, "sha256_textos": context["corpus"],
                    "prefijo_documento": embeddings.DOCUMENT_PREFIX, "prefijo_consulta": embeddings.QUERY_PREFIX}
        if any(manifest.get(key) != value for key, value in required.items()):
            raise ValueError("Production corpus vectors are stale or incompatible")
        layout = {"onnx/model_q4.onnx": "onnx/model.onnx", "onnx/model_q4.onnx_data": "onnx/model_q4.onnx_data",
                  "tokenizer.json": "tokenizer.json"}
        hashes = {key: digest(model / local) for key, local in layout.items()}
        if hashes != manifest["archivos"]:
            raise ValueError("q4 model does not match the corpus model")
        vectors = load_vectors(PROCESSED / f"embeddings/{embeddings.MODEL_NAME}.npy", rows)
    else:
        model = embeddings.MODELS_CACHE / "local/embeddinggemma-300m-fp32"
        # Pinned publisher files, installed separately. Preparation itself has no network activity.
        hashes = {key: digest(model / key) for key in FP32_HASHES}
        if hashes != FP32_HASHES:
            raise ValueError("fp32 files do not match the pinned publisher hashes")
        vectors = None
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = threads
    start = time.perf_counter()
    session = onnxruntime.InferenceSession(str(model / "onnx/model.onnx"), sess_options=options,
                                          providers=["CPUExecutionProvider"])
    embedder = embeddings.Embedder(session=session, tokenizer=embeddings.Embedder._load_tokenizer(model / "tokenizer.json"))
    load_seconds = time.perf_counter() - start
    rebuild_seconds = None
    corpus_reused = name == "q4"
    if vectors is None:
        vector_file = directory / "fp32-vectors.npy"
        identity_file = directory / "fp32-vectors.json"
        identity = {"context": {key: context[key] for key in ("corpus", "document_prefix", "max_tokens", "storage_dtype")},
                    "model_files": hashes}
        if vector_file.is_file() and identity_file.is_file():
            saved = json.loads(identity_file.read_text(encoding="utf-8"))
            if saved["identity"] != identity or saved["sha256"] != digest(vector_file):
                raise ValueError("Cached fp32 vectors belong to different inputs")
            vectors = np.load(vector_file, allow_pickle=False)
            rebuild_seconds = saved["rebuild_seconds"]
            corpus_reused = True
        else:
            start = time.perf_counter()
            batches = []
            for offset in range(0, len(rows), 8):
                batches.append(embedder.embed_documents([embeddings.document_text(row) for row in rows[offset:offset + 8]]))
                if offset % 80 == 0:
                    print(f"fp32 documents {min(offset + 8, len(rows))}/{len(rows)}", flush=True)
            vectors = np.concatenate(batches).astype(np.float16)
            rebuild_seconds = time.perf_counter() - start
            np.save(vector_file, vectors)
            write_json(identity_file, {"identity": identity, "sha256": digest(vector_file), "rebuild_seconds": rebuild_seconds})
    validate_vectors(vectors, len(rows))
    ids = [row["id_noticia"] for row in rows]
    lexical = BM25Index([Document.from_evidence(news_evidence(row)) for row in rows])
    rankings, hybrid, latencies = {}, {}, []
    embedder.embed_queries([queries[0]["consulta"]])  # same warmup, excludes cold initialization
    for query in queries:
        start = time.perf_counter()
        query_vector = embedder.embed_queries([query["consulta"]])[0]
        index = EmbeddingIndex(ids, vectors, lambda _: query_vector)
        semantic = index.search(query["consulta"], 20)
        latencies.append((time.perf_counter() - start) * 1000)
        rankings[query["qid"]] = [key for key, _ in semantic[:5]]
        bm25 = lexical.search(query["consulta"], 20)
        hybrid[query["qid"]] = [key for key, _ in hybrid_rrf([[key for key, _ in bm25],
                                                            [key for key, similarity in semantic if similarity >= MIN_COSINE]])[:5]]
    positions = {key: position for position, key in enumerate(ids)}
    membership = {position: group for group, members in enumerate(group_agglomerative(
        vectors, [datetime.fromisoformat(row["fecha_publicacion"].replace("Z", "+00:00")) for row in rows])) for position in members}
    predictions = {pair["id"]: membership[positions[pair["id_a"]]] == membership[positions[pair["id_b"]]] for pair in pairs}
    report = {"context": context, "rankings": rankings, "hybrid_rankings": hybrid, "pair_predictions": predictions,
              "provenance": {"repository": embeddings.MODEL_REPO, "revision": embeddings.MODEL_REVISION,
                             "files": hashes, "provider": session.get_providers(), "model": name,
                             "load_seconds": load_seconds, "corpus_rebuild_seconds": rebuild_seconds,
                             "corpus_reused": corpus_reused, "corpus_rebuild_this_run_seconds": None if corpus_reused else rebuild_seconds,
                             "warm_query_search_p50_ms": float(np.median(latencies)),
                             "warm_query_search_p95_ms": float(np.percentile(latencies, 95)), "peak_run_rss_mib": peak_rss_mib(),
                             "memory_scope": "entire isolated process including grouping; not the web app",
                             "latency_scope": "embedding + index creation + semantic search, excluding BM25, after one warmup"}}
    write_json(directory / f"{name}.json", report)
    print(json.dumps(report["provenance"], indent=2), flush=True)


def prepare(directory: Path, threads: int = 4) -> None:
    if threads < 1 or threads > 64:
        raise ValueError("CPU thread count must be between 1 and 64")
    if (directory / "snapshot.json").exists():
        raise ValueError("Comparison already frozen; use a new directory")
    directory.mkdir(parents=True, exist_ok=True)
    rows, queries, pairs, context = public_inputs()
    context["threads"] = threads
    reports = {}
    for name in ("q4", "fp32"):
        path = directory / f"{name}.json"
        if not path.exists():
            subprocess.run([sys.executable, "-m", "whoami.comparison_prepare", "--candidate", name,
                            "--directory", str(directory.resolve()), "--threads", str(threads)], check=True)
        report = json.loads(path.read_text(encoding="utf-8"))
        if name == "fp32":
            expected_files = FP32_HASHES
            installed_files = {key: digest(embeddings.MODELS_CACHE / "local/embeddinggemma-300m-fp32" / key) for key in expected_files}
        else:
            expected_files = json.loads((PROCESSED / "embeddings/manifest.json").read_text(encoding="utf-8"))["archivos"]
            layout = {"onnx/model_q4.onnx": "onnx/model.onnx", "onnx/model_q4.onnx_data": "onnx/model_q4.onnx_data",
                      "tokenizer.json": "tokenizer.json"}
            installed_files = {key: digest(embeddings.model_dir() / local) for key, local in layout.items()}
        if installed_files != expected_files:
            raise ValueError("Installed model differs from pinned candidate files")
        validate_cached_report(report, name, context, expected_files)
        reports[name] = report
    if reports["q4"]["provenance"]["files"]["tokenizer.json"] != reports["fp32"]["provenance"]["files"]["tokenizer.json"]:
        raise ValueError("Candidate tokenizers differ")
    lexical = BM25Index([Document.from_evidence(news_evidence(row)) for row in rows])
    candidates = {name: {"rankings": report["rankings"], "pair_predictions": report["pair_predictions"],
                         "provenance": report["provenance"]} for name, report in reports.items()}
    candidates.update({name + "_hybrid": {"rankings": report["hybrid_rankings"], "pair_predictions": None}
                       for name, report in reports.items()})
    candidates["bm25"] = {"rankings": {q["qid"]: [key for key, _ in lexical.search(q["consulta"], 5)] for q in queries},
                          "pair_predictions": None}
    snapshot = build_snapshot(rows, queries, candidates, pairs)
    snapshot.pop("fingerprint")
    snapshot["inputs"] = context
    snapshot["fingerprint"] = fingerprint(snapshot)
    write_json(directory / "snapshot.json", snapshot)
    print(f"Frozen {len(queries)} queries, {len(pairs)} pairs, {len(snapshot['items'])} blind decisions", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", choices=("q4", "fp32"), required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    run_candidate(args.candidate, args.directory, args.threads)
