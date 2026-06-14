"""Gemini API 재시도 유틸리티 (tenacity 기반, 최대 3회, 지수 백오프)."""
import logging

logger = logging.getLogger(__name__)

try:
    from tenacity import (
        retry,
        retry_if_exception,
        stop_after_attempt,
        wait_exponential,
        before_sleep_log,
    )

    def _is_retryable(exc: BaseException) -> bool:
        try:
            from google.genai import errors as _ge
            if isinstance(exc, _ge.ServerError):
                return True
            if isinstance(exc, _ge.ClientError):
                s = str(exc)
                return "429" in s or "quota" in s.lower() or "rate limit" in s.lower()
        except ImportError:
            pass
        import requests as _req
        return isinstance(exc, (_req.RequestException, ConnectionError, TimeoutError))

    gemini_retry = retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        retry=retry_if_exception(_is_retryable),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )

except ImportError:
    def gemini_retry(func):
        return func

__all__ = ["gemini_retry"]
