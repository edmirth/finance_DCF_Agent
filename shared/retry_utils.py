"""
Retry logic with exponential backoff for API calls.

This module provides a decorator for retrying function calls with exponential backoff,
specifically designed for handling transient failures in external API calls.
"""

import time
import random
import logging
from functools import wraps
from typing import Callable, Tuple, Type, Optional
import requests
from openai import APIError, RateLimitError

logger = logging.getLogger(__name__)


class RetryConfig:
    """Configuration for retry behavior"""
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: Tuple[Type[Exception], ...] = (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,  # Only 429, 500, 502, 503, 504
            APIError,
            RateLimitError,
        )
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions


def is_retryable_http_error(exception: Exception) -> bool:
    """Check if HTTP error is retryable (5xx, 429) vs permanent (4xx)"""
    if isinstance(exception, requests.exceptions.HTTPError):
        if hasattr(exception, 'response') and exception.response is not None:
            status_code = exception.response.status_code
            # Retry on rate limit and server errors
            # Do NOT retry on client errors (400, 401, 403, 404)
            return status_code in [429, 500, 502, 503, 504]
    return True  # Retry by default for non-HTTP exceptions


def calculate_backoff(attempt: int, config: RetryConfig) -> float:
    """Calculate exponential backoff delay with jitter"""
    delay = min(
        config.base_delay * (config.exponential_base ** attempt),
        config.max_delay
    )

    if config.jitter:
        # Add random jitter (±25% of delay)
        jitter_amount = delay * 0.25
        delay += random.uniform(-jitter_amount, jitter_amount)

    return max(0, delay)  # Ensure non-negative


def retry_with_backoff(config: Optional[RetryConfig] = None):
    """
    Decorator to retry function calls with exponential backoff.

    Usage:
        @retry_with_backoff()
        def my_api_call():
            return requests.get("https://api.example.com")

        @retry_with_backoff(RetryConfig(max_attempts=5, base_delay=2.0))
        def critical_api_call():
            return requests.post("https://api.example.com", json=data)
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            # Get function name safely for logging
            func_name = getattr(func, '__name__', 'unknown_function')

            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)

                except config.retryable_exceptions as e:
                    last_exception = e

                    # Check if this error should be retried
                    if not is_retryable_http_error(e):
                        logger.info(f"{func_name}: Non-retryable error (client error 4xx)")
                        raise  # Don't retry client errors

                    # Don't retry on last attempt
                    if attempt == config.max_attempts - 1:
                        logger.error(
                            f"{func_name}: Failed after {config.max_attempts} attempts. "
                            f"Last error: {type(e).__name__}: {e}"
                        )
                        raise

                    # Calculate backoff and wait
                    delay = calculate_backoff(attempt, config)
                    logger.warning(
                        f"{func_name}: Attempt {attempt + 1}/{config.max_attempts} failed "
                        f"with {type(e).__name__}: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    time.sleep(delay)

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception

        return wrapper
    return decorator
