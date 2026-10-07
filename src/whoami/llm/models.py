"""Models the project may call, with their free-tier limits and our own budget caps."""

from dataclasses import dataclass
from typing import Final, Literal


@dataclass(frozen=True)
class ModelLimits:
    name: str
    rpm: int
    tpm: int
    cap: int  # max network calls (chat) or texts (embedding) per budget window
    kind: Literal["chat", "embedding"]


MODELS: Final = {
    m.name: m
    for m in (
        ModelLimits("gemma-4-26b-a4b-it", rpm=30, tpm=16_000, cap=5_000, kind="chat"),
        ModelLimits("gemini-3.1-flash-lite", rpm=15, tpm=250_000, cap=200, kind="chat"),
        ModelLimits("gemini-3.5-flash-lite", rpm=15, tpm=250_000, cap=100, kind="chat"),
        ModelLimits("gemini-embedding-2", rpm=100, tpm=30_000, cap=900, kind="embedding"),
    )
}
