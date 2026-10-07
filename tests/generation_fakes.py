"""Test doubles shared by the generation tests: a fake `LLM` with canned JSON and small evidence builders."""

import json
from collections.abc import Callable, Iterable
from typing import Any

from whoami.llm.client import Completion, LLMError
from whoami.schemas import Evidence


class FakeLLM:
    """Same `complete` signature as `whoami.llm.LLM`; never touches the network.

    `responder` receives the call (a dict with `purpose`, `messages`, `evidence_ids`, `response_format`) and returns
    a dict or list (encoded as JSON), a string (returned as is) or an exception (raised).
    """

    def __init__(self, responder: Callable[[dict], Any] | Iterable[Any]) -> None:
        if callable(responder):
            self._responder = responder
        else:
            queue = iter(responder)
            self._responder = lambda call: next(queue)
        self.calls: list[dict] = []

    def complete(
        self,
        model: str,
        messages: list[dict],
        *,
        purpose: str,
        evidence_ids: Iterable[str] = (),
        response_format: dict | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> Completion:
        call = {
            "model": model,
            "messages": messages,
            "purpose": purpose,
            "evidence_ids": sorted(set(evidence_ids)),
            "response_format": response_format,
        }
        self.calls.append(call)
        result = self._responder(call)
        if isinstance(result, Exception):
            raise result
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        return Completion(text, model, False, 0, 0, 0.0)

    @property
    def n_calls(self) -> int:
        return len(self.calls)


def news(id_: str, **fields: str) -> Evidence:
    return Evidence(id_evidencia=id_, tipo="noticia", titulo="Titular", url="https://x.invalid", fecha=None, campos=fields)


def indicator(period: str = "2024", value: str = "44,36", unit: str = "% del PIB") -> Evidence:
    return Evidence(
        id_evidencia=f"WB-PAN-X-{period}",
        tipo="indicador",
        titulo="Indicador",
        url="https://x.invalid",
        fecha=None,
        campos={"indicador": "Exportaciones", "periodo": period, "valor": value, "unidad": unit},
    )


def by_id(*evidences: Evidence) -> dict[str, Evidence]:
    return {e.id_evidencia: e for e in evidences}


__all__ = ["FakeLLM", "LLMError", "by_id", "indicator", "news"]
