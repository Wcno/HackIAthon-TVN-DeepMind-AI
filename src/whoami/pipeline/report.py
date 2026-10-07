"""Plain-text summary of a pipeline run, for the terminal."""

from collections import Counter
from collections.abc import Mapping

from whoami.schemas import OutputSet


def format_summary(output: OutputSet, llm_calls: Mapping[str, tuple[int, int]] | None) -> str:
    """`llm_calls` is `{purpose: (cache hits, cache misses)}`, or `None` when the run used no LLM."""
    ranges = Counter(group.puntaje.rango for group in output.grupos)
    topics = Counter(group.tema for group in output.grupos)
    lines = [
        f"data/processed: {len(output.grupos)} grupos ({dict(ranges)}), {len(output.evidencias)} evidencias",
        f"grupos con varias noticias: {sum(group.n_noticias > 1 for group in output.grupos)}",
        "temas: " + ", ".join(f"{topic} {count}" for topic, count in topics.most_common()),
        f"grupos con contexto oficial: {sum(bool(group.contexto) for group in output.grupos)}",
    ]
    if not llm_calls:
        lines.append("llamadas LLM: ninguna")
    else:
        lines.append("llamadas LLM:")
        lines += [
            f"  {purpose}: {hits + misses} ({hits} en caché, {misses} a la red)"
            for purpose, (hits, misses) in llm_calls.items()
        ]
    return "\n".join(lines)
