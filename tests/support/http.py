"""Mock-transport helpers for provider tests. No real network traffic."""

from collections.abc import Callable

import httpx

Handler = Callable[[httpx.Request], httpx.Response]


class Recorder:
    """Replays queued responses/exceptions in order; the last one repeats."""

    def __init__(self, *outcomes: httpx.Response | Exception) -> None:
        self.requests: list[httpx.Request] = []
        self._outcomes = list(outcomes)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        outcome = self._outcomes.pop(0) if len(self._outcomes) > 1 else self._outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class Router:
    """Serves a fixed response per URL (query string ignored) and records requests."""

    def __init__(self, routes: dict[str, httpx.Response | Exception]) -> None:
        self.requests: list[httpx.Request] = []
        self._routes = routes

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url.copy_with(query=None))
        outcome = self._routes.get(url, httpx.Response(404))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


async def no_sleep(_: float) -> None:
    return None
