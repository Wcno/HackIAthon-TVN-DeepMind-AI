"""Corpus loading, paths and the text recipe shared by every experiment."""
import csv
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parents[1]
DATA = HERE / "datos"
NEWS = REPO / "data/processed/noticias.csv"
TEXT_RECIPE = "titulo + '. ' + descripcion (si hay descripción); si no, titulo"


def rows():
    with NEWS.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def text(row) -> str:
    title = row["titulo"].strip()
    desc = row["descripcion"].strip()
    return f"{title}. {desc}" if desc else title
