"""Freeze a validated G10 delivery and run it without providers or local inference.

Preparation copies existing outputs; it never downloads data, embeds, or generates.
The mutable SQLite database lives outside the hashed snapshot.
"""

import csv
import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

import numpy as np

from whoami import embeddings, store
from whoami.backend.service import quality_report
from whoami.backend.settings import Settings
from whoami.contracts import OUTPUTS, PROCESSED

STATIC = Path(__file__).parent / "backend/static"
OUTPUT_FILES = ("fichas.jsonl", "consultas.jsonl", "revisiones.jsonl", "revisiones_vinculadas.jsonl", "revisiones_historicas.jsonl")
REQUIRED_DATA = ("noticias.csv", "grupos.jsonl", "evidencias.jsonl", "manifest.json", "fuentes.json",
                 "calidad_noticias.json", "calidad_indicadores.json", "calidad_inec.json", "calidad_eventos.json",
                 "embeddings/manifest.json", f"embeddings/{embeddings.MODEL_NAME}.npy")


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def validate_snapshot(data: Path, outputs: Path) -> dict:
    """Reject partial, stale or broken deliveries before they can be rehearsed."""
    for name in REQUIRED_DATA:
        if not (data / name).is_file():
            raise ValueError(f"Missing offline input: {name}")
    integrity = quality_report(data)["manifest"].get("integrity", {})
    if integrity.get("status") != "verified":
        raise ValueError("Snapshot integrity is not verified; rebuild the data manifest before preparing the demo.")
    package = store.load(data, outputs)
    states = sorted({answer.estado for answer in package.consultas})
    if len(package.fichas) < 5 or not {"respondida", "abstencion"} <= set(states):
        raise ValueError("The offline demo needs five case files, a precomputed answer and an abstention.")
    if sum(case.borrador is not None for case in package.fichas) < 5:
        raise ValueError("The offline demo needs five precomputed drafts; insufficient cases can remain without a draft.")
    with (data / "noticias.csv").open(encoding="utf-8", newline="") as source:
        rows = [row for row in csv.DictReader(source) if row.get("fecha_publicacion")]
    manifest = json.loads((data / "embeddings/manifest.json").read_text(encoding="utf-8"))
    expected = {"modelo": embeddings.MODEL_REPO, "revision": embeddings.MODEL_REVISION,
                "dimensiones": embeddings.DIMENSIONS, "dtype": "float16", "receta_texto": embeddings.TEXT_RECIPE,
                "prefijo_documento": embeddings.DOCUMENT_PREFIX, "prefijo_consulta": embeddings.QUERY_PREFIX,
                "ids": [row["id_noticia"] for row in rows], "sha256_textos": embeddings.corpus_fingerprint(rows)}
    path = data / "embeddings" / f"{embeddings.MODEL_NAME}.npy"
    if any(manifest.get(key) != value for key, value in expected.items()) or manifest.get("sha256_vectores") != digest(path):
        raise ValueError("Stale or incompatible corpus vectors; run whoami embed before preparing the demo.")
    vectors = np.load(path, allow_pickle=False)
    if (vectors.shape != (len(rows), embeddings.DIMENSIONS) or vectors.dtype != np.float16
            or not np.isfinite(vectors).all() or np.any(np.linalg.norm(vectors.astype(np.float32), axis=1) == 0)):
        raise ValueError("Invalid precomputed corpus vectors.")
    return {"groups": len(package.grupos), "cases": len(package.fichas), "answers": len(package.consultas),
            "query_states": states, "embedded_news": len(rows)}


def prepare(destination: Path, data: Path = PROCESSED, outputs: Path = OUTPUTS) -> dict:
    """Publish a new immutable copy only after validating all inputs and assets."""
    destination = destination.resolve()
    if destination.exists():
        raise ValueError(f"Destination already exists: {destination}. Choose a new directory.")
    counts = validate_snapshot(data, outputs)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="offline-", dir=destination.parent) as temporary:
        staged = Path(temporary) / "bundle"
        target = staged / "data/processed"
        target.mkdir(parents=True)
        # Copy only delivery formats: no raw captures, caches, databases, credentials or models.
        for source in data.iterdir():
            if source.is_file() and source.suffix in {".json", ".jsonl", ".csv", ".geojson"}:
                shutil.copyfile(source, target / source.name)
        (target / "embeddings").mkdir()
        for name in ("manifest.json", f"{embeddings.MODEL_NAME}.npy"):
            shutil.copyfile(data / "embeddings" / name, target / "embeddings" / name)
        shutil.copyfile(data.parent / "manifest.json", staged / "data/manifest.json")
        (staged / "outputs").mkdir()
        for name in OUTPUT_FILES:
            if (outputs / name).is_file():
                shutil.copyfile(outputs / name, staged / "outputs" / name)
        benchmark = outputs / "offline/benchmark-consultas.jsonl"
        if benchmark.is_file():
            answers = store.read_jsonl(outputs / "consultas.jsonl")
            existing = {answer["id_consulta"] for answer in answers}
            answers.extend(answer for answer in store.read_jsonl(benchmark) if answer["id_consulta"] not in existing)
            store.write_jsonl(staged / "outputs/consultas.jsonl", answers)
        counts = validate_snapshot(target, staged / "outputs")
        shutil.copytree(STATIC, staged / "static", ignore=shutil.ignore_patterns("src"))
        manifest = {"format": 1, "created_at": datetime.now(UTC).isoformat(), "counts": counts,
                    "sha256": {file.relative_to(staged).as_posix(): digest(file)
                               for file in sorted(staged.rglob("*")) if file.is_file()}}
        (staged / "offline.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        verify(staged)
        staged.rename(destination)
    return counts


def verify(bundle: Path) -> dict:
    """Verify hashes and the full contract without opening a model or contacting a provider."""
    root = bundle.resolve()
    manifest = json.loads((root / "offline.json").read_text(encoding="utf-8"))
    hashes = manifest.get("sha256")
    if manifest.get("format") != 1 or not isinstance(hashes, dict) or not hashes:
        raise ValueError("Unsupported or empty offline manifest.")
    required = {f"data/processed/{name}" for name in REQUIRED_DATA} | {
        "data/manifest.json", "outputs/fichas.jsonl", "outputs/consultas.jsonl", "outputs/revisiones.jsonl",
        "static/app.css", "static/htmx.min.js", "static/editor.js", "static/shell.js"}
    css = root / "static/app.css"
    if css.is_file():
        required.update("static/" + name for name in re.findall(r"url\(['\"]?/static/([^)'\"]+)", css.read_text(encoding="utf-8")))
    if not required <= hashes.keys():
        raise ValueError("Offline manifest omits required delivery files.")
    for name, expected in hashes.items():
        relative = PurePosixPath(name)
        path = (root / name).resolve()
        if relative.is_absolute() or ".." in relative.parts or not path.is_relative_to(root):
            raise ValueError(f"Unsafe offline path: {name}")
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"Missing or changed offline file: {name}")
    counts = validate_snapshot(root / "data/processed", root / "outputs")
    if counts != manifest.get("counts"):
        raise ValueError("Offline manifest counts do not match its snapshot.")
    return counts


def offline_settings(bundle: Path, database: Path | None = None) -> Settings:
    """Explicit offline settings override all ambient .env/provider configuration."""
    verify(bundle)
    root = bundle.resolve()
    return Settings(database=database or root / "runtime/editorial.sqlite3", demo=False, offline=True,
                    data_directory=root / "data/processed", output_directory=root / "outputs",
                    static_directory=root / "static")


def add_arguments(parser) -> None:
    commands = parser.add_subparsers(dest="offline_command", required=True)
    prepare_command = commands.add_parser("prepare", help="freeze the existing validated corpus and precomputed outputs")
    prepare_command.add_argument("--output", type=Path, required=True)
    prepare_command.add_argument("--data", type=Path, default=PROCESSED)
    prepare_command.add_argument("--outputs", type=Path, default=OUTPUTS)
    for command in ("verify", "serve"):
        child = commands.add_parser(command)
        child.add_argument("--bundle", type=Path, required=True)
        if command == "serve":
            child.add_argument("--database", type=Path)
            child.add_argument("--port", type=int, default=8000)


def main(args) -> int:
    if args.offline_command == "prepare":
        print(json.dumps(prepare(args.output, args.data, args.outputs)))
    elif args.offline_command == "verify":
        print(json.dumps(verify(args.bundle)))
    else:
        import uvicorn
        from whoami.backend.app import create_app

        uvicorn.run(create_app(offline_settings(args.bundle, args.database)), host="127.0.0.1", port=args.port)
    return 0
