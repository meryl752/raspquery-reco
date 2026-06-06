"""Retries fournisseurs LLM — aligné sur stackai/lib/llm/retry.ts."""

from __future__ import annotations

import asyncio
import logging
import random
import re
from collections.abc import Awaitable, Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_TRANSIENT_RE = re.compile(
    r"429|503|502|408|500|rate.?limit|overloaded|timeout|timed out|"
    r"ETIMEDOUT|ECONNRESET|ECONNREFUSED|fetch failed|network|socket|"
    r"temporarily|try again|queue_exceeded",
    re.I,
)


def error_message(err: BaseException) -> str:
    return str(err)


def is_transient_provider_error(err: BaseException) -> bool:
    msg = error_message(err)
    if _TRANSIENT_RE.search(msg):
        return True
    status = getattr(err, "status", None) or getattr(err, "code", None)
    if status in (429, 503, 502, 408):
        return True
    cause = getattr(err, "__cause__", None)
    code = getattr(cause, "code", None) if cause else None
    return code in ("ECONNRESET", "ETIMEDOUT")


def compute_provider_backoff_ms(err: BaseException, attempt_index: int) -> int:
    msg = error_message(err)
    ms_match = re.search(r"try again in (\d+)\s*ms", msg, re.I)
    if ms_match:
        n = int(ms_match.group(1))
        if n >= 0:
            return min(20_000, max(80, n + 80))
    sec_match = re.search(r"try again in (\d+(?:\.\d+)?)\s*s(?:ec)?", msg, re.I)
    if sec_match:
        s = float(sec_match.group(1))
        if s >= 0:
            return min(20_000, max(200, round(s * 1000) + 100))
    base = 350 * (2**attempt_index)
    jitter = random.randint(0, 199)
    return min(14_000, base + jitter)


async def with_provider_retries(
    label: str,
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 4,
) -> T:
    last_err: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return await fn()
        except BaseException as err:
            last_err = err
            last = attempt == max_attempts - 1
            if last or not is_transient_provider_error(err):
                raise
            delay_ms = compute_provider_backoff_ms(err, attempt)
            logger.warning(
                "%s: échec transitoire (%s), nouvel essai dans %dms (%d/%d)",
                label,
                error_message(err)[:120],
                delay_ms,
                attempt + 1,
                max_attempts,
            )
            await asyncio.sleep(delay_ms / 1000.0)
    assert last_err is not None
    raise last_err
