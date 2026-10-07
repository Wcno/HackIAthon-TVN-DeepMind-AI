"""Keyword baseline for topic classification (G7 baseline).

Copied from `src/ai/classifier.py` of the branch `origin/mvp-jwhoami` (`keyword_baseline`): same keyword lists
and scoring (substring hits, confidence = hits / 3 capped at 1), with topics mapped to the contract slugs and ONE
change: no hit returns `sin_tema`, where the original defaulted to economy.
"""

import re

from whoami.contracts import NO_TOPIC, TOPICS

METHOD = "palabras_clave_v1"

_TOPIC_KEYWORDS = {
    "economia": ("inflación", "empleo", "banco", "exportación", "economía"),
    "logistica_canal": ("canal", "puerto", "buque", "tránsito", "logística"),
    "turismo": ("turismo", "hotel", "visitante", "viajero", "destino"),
    "servicios_publicos": ("agua", "hospital", "transporte", "energía", "servicio"),
    "eventos_naturales": ("sismo", "terremoto", "lluvia", "sequía", "huracán"),
    "regulacion": ("ley", "norma", "regulación", "decreto", "regulador"),
}

HITS_FOR_FULL_CONFIDENCE = 3


def _classify(text: str) -> tuple[str, float, str]:
    normalized = re.sub(r"\s+", " ", text.casefold())
    scores = {
        topic: sum(normalized.count(keyword) for keyword in keywords) for topic, keywords in _TOPIC_KEYWORDS.items()
    }
    topic, score = max(scores.items(), key=lambda item: (item[1], -TOPICS.index(item[0])))
    if score == 0:
        return NO_TOPIC, 0.0, METHOD
    return topic, min(score / HITS_FOR_FULL_CONFIDENCE, 1.0), METHOD


def classify_keywords(texts: list[str]) -> list[tuple[str, float, str]]:
    return [_classify(text) for text in texts]
