"""Retrieval over the evidence corpus: BM25 (pure Python), embeddings and reciprocal rank fusion."""

import math
import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from whoami.generation.verifier import fold
from whoami.schemas import Evidence

BM25_K1 = 1.5
BM25_B = 0.75
RRF_K = 60

ScoredId = tuple[str, float]

#: Folded (lowercase, no accents). Question words are included: they carry no topic.
STOPWORDS = frozenset(
    """a al algo algun alguna algunas alguno algunos ante antes aqui asi aun cada como con contra cual cuales cuando
    cuanta cuantas cuanto cuantos de del desde donde dos e el ella ellas ellos en entre era eran es esa esas ese eso
    esos esta estaba estan estar este esto estos fue fueron ha han hasta hay la las le les lo los mas me mi mis muy
    ni no nos o otra otras otro otros para pero poco por porque que quien quienes se ser si sin sobre son su sus
    tambien tan tanto te tiene todo todos tu tus un una uno unos y ya yo""".split()
)

_WORD = re.compile(r"[a-z0-9]+")
_VOWELS = "aeiou"


def _stem(word: str) -> str:
    """Light Spanish stemming: `ciones` to `cion`, plural `es` after a consonant, plural `s`."""
    if word.endswith("ciones"):
        return word[:-6] + "cion"
    if len(word) > 4 and word.endswith("es") and word[-3] not in _VOWELS:
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("sis"):
        return word[:-1]
    return word


def tokenize(text: str) -> list[str]:
    return [_stem(word) for word in _WORD.findall(fold(text)) if word not in STOPWORDS]


@dataclass(frozen=True)
class Document:
    id_evidencia: str
    text: str

    @classmethod
    def from_evidence(cls, evidence: Evidence) -> "Document":
        return cls(evidence.id_evidencia, "\n".join([evidence.titulo, *evidence.campos.values()]))


def documents_from(evidences: Iterable[Evidence]) -> list[Document]:
    return [Document.from_evidence(evidence) for evidence in evidences]


def _top(scores: dict[str, float], k: int) -> list[ScoredId]:
    ranked = sorted(((i, s) for i, s in scores.items() if s > 0), key=lambda pair: (-pair[1], pair[0]))
    return ranked[:k]


class Retriever(Protocol):
    def search(self, query: str, k: int) -> list[ScoredId]: ...


class BM25Index:
    """Okapi BM25 (k1=1.5, b=0.75) over tokens that are accent-free, stop-word-free and lightly stemmed."""

    def __init__(self, documents: Sequence[Document]) -> None:
        self._frequencies = {d.id_evidencia: Counter(tokenize(d.text)) for d in documents}
        self._lengths = {i: sum(counts.values()) for i, counts in self._frequencies.items()}
        total = sum(self._lengths.values())
        self._average_length = total / len(documents) if documents else 0.0
        self._document_frequency = Counter(term for counts in self._frequencies.values() for term in counts)

    def _idf(self, term: str) -> float:
        n, df = len(self._frequencies), self._document_frequency[term]
        return math.log((n - df + 0.5) / (df + 0.5) + 1)

    def search(self, query: str, k: int) -> list[ScoredId]:
        terms = [term for term in dict.fromkeys(tokenize(query)) if term in self._document_frequency]
        scores: dict[str, float] = {}
        for doc_id, counts in self._frequencies.items():
            length_norm = BM25_K1 * (1 - BM25_B + BM25_B * self._lengths[doc_id] / self._average_length)
            scores[doc_id] = sum(
                self._idf(term) * counts[term] * (BM25_K1 + 1) / (counts[term] + length_norm)
                for term in terms
                if counts[term]
            )
        return _top(scores, k)


def _unit(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.where(norms == 0, 1.0, norms)


class EmbeddingIndex:
    """Cosine top-k over normalized vectors. `embed_query` turns the query into a vector of the same space."""

    def __init__(self, ids: Sequence[str], vectors: np.ndarray, embed_query: Callable[[str], np.ndarray]) -> None:
        self._ids = list(ids)
        self._vectors = _unit(np.asarray(vectors, dtype=np.float64))
        self._embed_query = embed_query

    def search(self, query: str, k: int) -> list[ScoredId]:
        similarities = self._vectors @ _unit(np.asarray(self._embed_query(query), dtype=np.float64))
        order = sorted(range(len(self._ids)), key=lambda n: (-similarities[n], self._ids[n]))
        return [(self._ids[n], float(similarities[n])) for n in order[:k]]


def hybrid_rrf(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> list[ScoredId]:
    """Reciprocal rank fusion: each ranking gives `1 / (k + rank)` to its ids."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


class BM25Retriever:
    def __init__(self, index: BM25Index) -> None:
        self._index = index

    def search(self, query: str, k: int) -> list[ScoredId]:
        return self._index.search(query, k)


class EmbeddingRetriever:
    def __init__(self, index: EmbeddingIndex) -> None:
        self._index = index

    def search(self, query: str, k: int) -> list[ScoredId]:
        return self._index.search(query, k)


class HybridRetriever:
    """Fuses the rankings of several retrievers. Scores are RRF scores (about 0.03 at best), not BM25 or cosine."""

    def __init__(self, retrievers: Sequence[Retriever], pool: int = 20, rrf_k: int = RRF_K) -> None:
        self._retrievers = list(retrievers)
        self._pool = pool
        self._rrf_k = rrf_k

    def search(self, query: str, k: int) -> list[ScoredId]:
        rankings = [[i for i, _ in retriever.search(query, self._pool)] for retriever in self._retrievers]
        return hybrid_rrf(rankings, self._rrf_k)[:k]
