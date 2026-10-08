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


#: Share of the published RPM and TPM the limiter targets. Google counts per calendar minute and the quota
#: is shared by every process on the project key, so a sliding window at 100 % still peaked at 32/30 RPM.
RATE_HEADROOM: Final = 0.8
#: Tokens get a wider margin: our estimate before the call is approximate, and a 1.5K-token judge run at 100 %
#: still peaked at 14.66K of Gemma's 16K TPM.
TOKEN_HEADROOM: Final = 0.7

MODELS: Final = {
    m.name: m
    for m in (
        ModelLimits("gemma-4-26b-a4b-it", rpm=30, tpm=16_000, cap=5_000, kind="chat"),
        ModelLimits("gemini-3.1-flash-lite", rpm=15, tpm=250_000, cap=200, kind="chat"),
        ModelLimits("gemini-3.5-flash-lite", rpm=15, tpm=250_000, cap=200, kind="chat"),
        # The embedding endpoint counts texts, not requests: 100 texts per minute (measured, ADR-0001).
        ModelLimits("gemini-embedding-2", rpm=100, tpm=30_000, cap=900, kind="embedding"),
    )
}
