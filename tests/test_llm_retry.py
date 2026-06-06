import pytest

from app.infra.llm.retry import (
    compute_provider_backoff_ms,
    is_transient_provider_error,
    with_provider_retries,
)


class Fake429(RuntimeError):
    pass


def test_is_transient_429():
    assert is_transient_provider_error(Fake429("Cerebras HTTP 429: queue_exceeded"))


def test_is_not_transient_400():
    assert not is_transient_provider_error(RuntimeError("Cerebras HTTP 400: bad request"))


def test_backoff_parses_try_again_ms():
    err = RuntimeError("Rate limit — try again in 1200 ms")
    assert compute_provider_backoff_ms(err, 0) >= 1280


@pytest.mark.asyncio
async def test_with_provider_retries_eventually_succeeds():
    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("HTTP 429 rate limit")
        return "ok"

    out = await with_provider_retries("test", flaky, max_attempts=3)
    assert out == "ok"
    assert calls["n"] == 2
