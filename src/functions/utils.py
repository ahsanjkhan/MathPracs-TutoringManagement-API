import logging
import time
from functools import wraps

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
RETRY_DELAY = 5  # seconds (exponential: 5, 10, 20, 40, 80s)


def retry_on_error(retryable_errors: list[str] = None):
    """
    Decorator to retry on specific errors with exponential backoff.

    Args:
        retryable_errors: List of error substrings to retry on.
                         Defaults to common rate limit errors.
    """
    if retryable_errors is None:
        retryable_errors = [
            "userRateLimitExceeded",   # Google
            "rateLimitExceeded",       # Google
            "RATE_LIMIT_EXCEEDED",     # Google Meet
            "Quota exceeded",          # Google quota errors
            "429",                     # HTTP 429 Too Many Requests
            "too_many_requests",       # Dropbox
            "too_many_write_operations",  # Dropbox
            "rate_limit",              # Generic
        ]

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(MAX_RETRIES):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_str = str(e)
                    is_retryable = any(err in error_str for err in retryable_errors)

                    if is_retryable and attempt < MAX_RETRIES - 1:
                        wait_time = RETRY_DELAY * (2 ** attempt)
                        logger.warning(f"Retryable error in {func.__name__}, retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        raise
        return wrapper
    return decorator
