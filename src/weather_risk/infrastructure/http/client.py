"""Shared GET-with-retry used by every HTTP data provider.

Each provider passes its own application error types, so httpx exceptions never leak and
weather and hazard failures stay distinguishable.
"""

import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

import httpx

from weather_risk.infrastructure.http.retry import RetryPolicy

logger = logging.getLogger(__name__)

_MAX_ERROR_DETAIL_CHARS = 200


@dataclass(frozen=True, slots=True)
class ProviderErrors:
    """The application errors a provider raises for each kind of HTTP failure."""

    timeout: Callable[[str], Exception]
    unavailable: Callable[[str], Exception]
    response: Callable[[int, str], Exception]


async def get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    source: str,
    timeout_seconds: float,
    retry_policy: RetryPolicy,
    errors: ProviderErrors,
    sleep: Callable[[float], Awaitable[None]],
    params: Mapping[str, str] | None = None,
) -> httpx.Response:
    """GET ``url``; retry transient failures per ``retry_policy``; raise ``errors`` types."""
    error: Exception | None = None

    for attempt in range(1, retry_policy.max_attempts + 1):
        try:
            response = await client.get(url, params=params, timeout=timeout_seconds)
        except httpx.TimeoutException as exc:
            error = errors.timeout(f"{source} did not respond within {timeout_seconds}s")
            error.__cause__ = exc
        except httpx.RequestError as exc:
            error = errors.unavailable(f"Could not reach {source}: {type(exc).__name__}")
            error.__cause__ = exc
        else:
            if response.is_success:
                return response
            error = errors.response(response.status_code, error_detail(response))
            if not retry_policy.is_retryable_status(response.status_code):
                raise error

        if attempt < retry_policy.max_attempts:
            delay = retry_policy.delay_before_retry(attempt)
            logger.warning(
                "%s attempt %d/%d failed (%s); retrying in %.2fs",
                source,
                attempt,
                retry_policy.max_attempts,
                error,
                delay,
            )
            await sleep(delay)

    assert error is not None
    raise error


def error_detail(response: httpx.Response) -> str:
    """Best-effort short reason from an error body (e.g. Open-Meteo's {"reason": "..."})."""
    try:
        body = response.json()
        reason = body.get("reason") or body.get("message") or ""
    except (ValueError, AttributeError):
        reason = response.text
    return str(reason)[:_MAX_ERROR_DETAIL_CHARS]
