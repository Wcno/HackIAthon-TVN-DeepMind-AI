"""Per-model requests-per-minute and tokens-per-minute limiter over a 60 s sliding window."""

from collections import deque
from collections.abc import Callable

WINDOW_S = 60.0


class RateLimiter:
    def __init__(
        self,
        rpm: int,
        tpm: int,
        clock: Callable[[], float],
        sleep: Callable[[float], None],
    ) -> None:
        self._rpm = rpm
        self._tpm = tpm
        self._clock = clock
        self._sleep = sleep
        self._requests: deque[list[float]] = deque()  # [timestamp, tokens]

    def acquire(self, tokens: int) -> None:
        while (wait := self._wait_needed(tokens)) > 0:
            self._sleep(wait)
        self._requests.append([self._clock(), tokens])

    def adjust(self, estimated: int, actual: int) -> None:
        if self._requests and self._requests[-1][1] == estimated:
            self._requests[-1][1] = actual

    def _wait_needed(self, tokens: int) -> float:
        now = self._clock()
        while self._requests and self._requests[0][0] <= now - WINDOW_S:
            self._requests.popleft()
        if not self._requests:
            return 0.0
        if len(self._requests) >= self._rpm:
            return self._requests[0][0] + WINDOW_S - now
        used = sum(request_tokens for _, request_tokens in self._requests)
        if used + tokens <= self._tpm:
            return 0.0
        return self._time_until_tokens_fit(tokens, now, used)

    def _time_until_tokens_fit(self, tokens: int, now: float, used: int) -> float:
        for timestamp, request_tokens in self._requests:
            used -= request_tokens
            if used + tokens <= self._tpm:
                return timestamp + WINDOW_S - now
        return self._requests[-1][0] + WINDOW_S - now
