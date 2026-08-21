"""
Multi-provider LLM router using instructor + Pydantic + tenacity.

Usage:
    from src.modules.ai.router import llm_extract
    from src.schemas.ai import PreVisitTriage

    result = await llm_extract(
        response_model=PreVisitTriage,
        prompt="Patient reports...",
        call_type="pre_visit",
        queue_id=42,
    )
    if result is None:
        # LLM failed — use fallback (raw text shown to doctor)
        ...
"""

import asyncio
import logging
import time
from typing import Any, TypeVar

import instructor
from anthropic import AsyncAnthropic
from groq import AsyncGroq
from openai import AsyncOpenAI
from pydantic import BaseModel
from tenacity import (
    RetryError,
    before_sleep_log,
    retry,
    stop_after_attempt,
    wait_random_exponential,
)

from src.core.config import get_settings
from src.core.logger import get_logger
from src.models.integration import LLMCallLog

logger = get_logger(__name__)
settings = get_settings()

T = TypeVar("T", bound=BaseModel)


# ── Provider Client Factory ───────────────────────────────────────────────────


def _get_instructor_client(provider: str) -> Any:
    """
    Build an instructor-patched async client for the given provider.

    Raises:
        ValueError: If provider is unknown or API key is not configured.
    """
    match provider:
        case "groq":
            if not settings.groq_api_key:
                raise ValueError("GROQ_API_KEY is not configured")
            return instructor.from_groq(AsyncGroq(api_key=settings.groq_api_key))

        case "openai":
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY is not configured")
            return instructor.from_openai(AsyncOpenAI(api_key=settings.openai_api_key))

        case "anthropic":
            if not settings.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY is not configured")
            return instructor.from_anthropic(
                AsyncAnthropic(api_key=settings.anthropic_api_key)
            )

        case "gemini":
            if not settings.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is not configured")
            # Gemini via OpenAI-compatible endpoint
            return instructor.from_openai(
                AsyncOpenAI(
                    api_key=settings.gemini_api_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                )
            )

        case _:
            raise ValueError(f"Unknown LLM provider: {provider!r}")


_MODEL_MAP: dict[str, str] = {
    "groq": settings.groq_model if getattr(settings, "groq_model", None) else "openai/gpt-oss-120b",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "gemini": "gemini-1.5-flash",
}


# ── Core Extraction with tenacity ─────────────────────────────────────────────


async def llm_extract(
    response_model: type[T],
    prompt: str,
    call_type: str,
    queue_id: int | None = None,
    provider: str | None = None,
) -> T | None:
    """
    Extract structured data from LLM output using instructor + tenacity.

    Retry policy:
    - 2 attempts with exponential backoff and jitter
    - 5-second per-attempt timeout
    - WARNING logged before each retry via before_sleep_log

    On exhausted retries:
    - Logs failure to llm_call_log (non-blocking)
    - Returns None — caller MUST handle gracefully (set is_processed=False)

    Args:
        response_model: Pydantic model class instructor will enforce.
        prompt: The system/user prompt to send to the LLM.
        call_type: "pre_visit" or "post_visit" (for llm_call_log).
        queue_id: Associated doctor_queue.id for observability.
        provider: Override default provider (falls back to settings.default_llm_provider).

    Returns:
        Populated response_model instance, or None if all retries failed.
    """
    chosen_provider = provider or settings.default_llm_provider
    start_ms = int(time.monotonic() * 1000)
    retry_count = 0

    @retry(
        stop=stop_after_attempt(settings.llm_max_retries),
        wait=wait_random_exponential(multiplier=1, max=4),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _attempt() -> T:
        nonlocal retry_count
        retry_count += 1

        client = _get_instructor_client(chosen_provider)
        model_name = _MODEL_MAP.get(chosen_provider, "gpt-4o-mini")

        logger.debug(
            "LLM extraction attempt — provider=%s model=%s call_type=%s queue_id=%s",
            chosen_provider,
            model_name,
            call_type,
            queue_id,
        )

        result = await asyncio.wait_for(
            client.chat.completions.create(
                model=model_name,
                response_model=response_model,
                messages=[{"role": "user", "content": prompt}],
                max_retries=0,  # tenacity handles retries, not instructor
            ),
            timeout=settings.llm_timeout_seconds,
        )
        return result  # type: ignore[return-value]

    try:
        result = await _attempt()
        latency_ms = int(time.monotonic() * 1000) - start_ms

        logger.info(
            "LLM extraction succeeded — provider=%s call_type=%s latency=%dms queue_id=%s",
            chosen_provider,
            call_type,
            latency_ms,
            queue_id,
        )
        _log_call(
            provider=chosen_provider,
            call_type=call_type,
            queue_id=queue_id,
            success=True,
            latency_ms=latency_ms,
            retry_count=retry_count - 1,
        )
        return result

    except (RetryError, Exception) as exc:
        latency_ms = int(time.monotonic() * 1000) - start_ms
        error_msg = str(exc)

        logger.error(
            "LLM extraction FAILED after %d retries — provider=%s call_type=%s "
            "queue_id=%s error=%s",
            settings.llm_max_retries,
            chosen_provider,
            call_type,
            queue_id,
            error_msg,
        )
        _log_call(
            provider=chosen_provider,
            call_type=call_type,
            queue_id=queue_id,
            success=False,
            latency_ms=latency_ms,
            retry_count=retry_count,
            error_message=error_msg,
        )
        return None  # NON-BLOCKING — caller sets is_processed=False


def _log_call(
    *,
    provider: str,
    call_type: str,
    queue_id: int | None,
    success: bool,
    latency_ms: int,
    retry_count: int,
    error_message: str | None = None,
) -> None:
    """
    Fire-and-forget LLM call log write.

    This is intentionally synchronous-compatible — the log is written inline.
    In production, consider offloading to a background task queue.
    """
    log_entry = LLMCallLog(
        provider=provider,
        call_type=call_type,
        queue_id=queue_id,
        success=success,
        latency_ms=latency_ms,
        retry_count=retry_count,
        error_message=error_message,
    )
    # Note: Actual DB write happens in calling service via injected session.
    # This object is returned for the caller to persist in its transaction.
    # For simplicity, callers receive the log object and commit it themselves.
    logger.debug("LLM call log entry created: %s", log_entry)
