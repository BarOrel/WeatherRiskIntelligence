from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded retry policy for transient HTTP/transport failures.

    ``max_retries`` counts retries after the first attempt. Delays grow exponentially:
    ``backoff_seconds``, then 2x, 4x, ...
    """

    max_retries: int = 2
    backoff_seconds: float = 0.5

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError(f"max_retries must not be negative, got {self.max_retries}")
        if self.backoff_seconds < 0:
            raise ValueError(
                f"backoff_seconds must not be negative, got {self.backoff_seconds}"
            )

    @property
    def max_attempts(self) -> int:
        return self.max_retries + 1

    def delay_before_retry(self, retry_number: int) -> float:
        """Delay before the given retry (1-based)."""
        return self.backoff_seconds * 2 ** (retry_number - 1)

    @staticmethod
    def is_retryable_status(status_code: int) -> bool:
        """429 and 5xx are transient; other 4xx are the caller's fault and never retried."""
        return status_code == 429 or status_code >= 500
