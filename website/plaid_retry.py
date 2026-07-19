"""Bounded exponential retry for eligible Plaid API requests.

The caller decides whether an endpoint is safe to retry and which raised
errors are transient. Keeping those decisions outside the runner prevents a
transport helper from retrying non-idempotent operations by accident.
"""
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar


ResultT = TypeVar('ResultT')


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for a bounded exponential retry sequence."""

    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    multiplier: float = 2.0
    max_delay_seconds: float = 4.0

    def __post_init__(self) -> None:
        """Reject settings that cannot produce a valid retry sequence."""
        if self.max_attempts < 1:
            raise ValueError('max_attempts must be at least 1')
        if self.base_delay_seconds < 0:
            raise ValueError('base_delay_seconds must be non-negative')
        if self.multiplier < 1:
            raise ValueError('multiplier must be at least 1')
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError('max_delay_seconds must be >= base_delay_seconds')


class PlaidRetry:
    """Run eligible Plaid operations with bounded exponential backoff."""

    def __init__(
        self,
        config: RetryConfig | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Create a retry runner with injectable sleeping for fast tests."""
        self.config: RetryConfig = config or RetryConfig()
        self._sleep: Callable[[float], None] = sleep

    def delay_seconds(self, failed_attempt: int) -> float:
        """Return the delay in seconds after a failed 1-indexed attempt."""
        if failed_attempt < 1:
            raise ValueError('failed_attempt must be at least 1')
        delay_seconds: float = (
            self.config.base_delay_seconds
            * (self.config.multiplier ** (failed_attempt - 1))
        )
        return min(delay_seconds, self.config.max_delay_seconds)

    def run(
        self,
        operation: Callable[[], ResultT],
        error_type: type[Exception],
        is_retryable: Callable[[Exception], bool],
    ) -> ResultT:
        """Run an operation until success, a terminal error, or exhaustion."""
        attempt: int = 1
        while True:
            try:
                return operation()
            except error_type as error:
                if attempt >= self.config.max_attempts or not is_retryable(error):
                    raise
                delay_seconds: float = self.delay_seconds(attempt)
                print(
                    f'[plaid-retry] attempt {attempt} failed; '
                    f'retrying in {delay_seconds:.2f}s'
                )
                self._sleep(delay_seconds / 1000)
                attempt += 1
