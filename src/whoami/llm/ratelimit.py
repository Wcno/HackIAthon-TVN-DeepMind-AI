"""Per-model requests-per-minute and tokens-per-minute limiter over a 60 s sliding window, safe across threads.

A request can weigh more than one unit: the embedding endpoint limits texts per minute, not requests.
"""

import threading
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
        self._requests: deque[list[float]] = deque()  # [timestamp, tokens, units]
        self._lock = threading.Lock()

    def acquire(self, tokens: int, units: int = 1) -> None:
        with self._lock:
            while (wait := self._wait_needed(tokens, units)) > 0:
                self._sleep(wait)
            self._requests.append([self._clock(), tokens, units])

    def adjust(self, estimated: int, actual: int) -> None:
        with self._lock:
            for request in reversed(self._requests):
                if request[1] == estimated:
                    request[1] = actual
                    return

    def _wait_needed(self, tokens: int, units: int = 1) -> float:
        now = self._clock()
        while self._requests and self._requests[0][0] <= now - WINDOW_S:
            self._requests.popleft()
        if not self._requests:
            return 0.0
        if sum(request[2] for request in self._requests) + units > self._rpm:
            return self._time_until_units_fit(units, now)
        used = sum(request[1] for request in self._requests)
        if used + tokens <= self._tpm:
            return 0.0
        return self._time_until_tokens_fit(tokens, now, used)

    def _time_until_tokens_fit(self, tokens: int, now: float, used: int) -> float:
        for timestamp, request_tokens, _ in self._requests:
            used -= request_tokens
            if used + tokens <= self._tpm:
                return timestamp + WINDOW_S - now
        return self._requests[-1][0] + WINDOW_S - now

    def _time_until_units_fit(self, units: int, now: float) -> float:
        used = sum(request[2] for request in self._requests)
        for timestamp, _, request_units in self._requests:
            used -= request_units
            if used + units <= self._rpm:
                return timestamp + WINDOW_S - now
        return self._requests[-1][0] + WINDOW_S - now
