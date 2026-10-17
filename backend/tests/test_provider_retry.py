import pytest

from app.providers.base import ProviderError
from app.providers.gemini import classify_client_error
from app.providers.openai_compat import classify_openai_error
from app.providers.retry import call_with_retry


def test_retry_transient_error_eventually_succeeds():
    attempts = 0
    sleeps: list[float] = []

    def mock_fn():
        nonlocal attempts
        attempts += 1
        if attempts < 4:
            raise ProviderError("transient", "503 Service Unavailable")
        return "ok"

    result = call_with_retry(
        mock_fn,
        provider_name="TestProvider",
        max_retries=6,
        sleep_fn=sleeps.append,
        limiter=None,
    )
    assert result == "ok"
    assert attempts == 4
    assert len(sleeps) == 3
    # Delays should increase exponentially (approx 5s, 10s, 20s + jitter)
    assert 5.0 <= sleeps[0] <= 8.0
    assert 10.0 <= sleeps[1] <= 13.0
    assert 20.0 <= sleeps[2] <= 23.0


def test_retry_transient_exhausts_retries():
    attempts = 0
    sleeps: list[float] = []

    def mock_fn():
        nonlocal attempts
        attempts += 1
        raise ProviderError("transient", "500 Internal Error")

    with pytest.raises(ProviderError) as exc_info:
        call_with_retry(
            mock_fn,
            provider_name="TestProvider",
            max_retries=6,
            sleep_fn=sleeps.append,
            limiter=None,
        )
    assert exc_info.value.category == "transient"
    assert attempts == 7  # Initial attempt + 6 retries
    assert len(sleeps) == 6


def test_does_not_retry_non_transient_errors():
    sleeps: list[float] = []

    for cat in ("quota", "permanent", "invalid_output"):
        calls = 0

        def mock_fn():
            nonlocal calls
            calls += 1
            raise ProviderError(cat, f"Error of type {cat}")

        with pytest.raises(ProviderError) as exc_info:
            call_with_retry(
                mock_fn,
                provider_name="TestProvider",
                max_retries=6,
                sleep_fn=sleeps.append,
                limiter=None,
            )
        assert exc_info.value.category == cat
        assert calls == 1
    assert len(sleeps) == 0


def test_gemini_classify_client_error():
    # 429 daily quota
    err_quota = classify_client_error(
        429, "Quota exceeded for quota metric 'Generate Content API requests per day'"
    )
    assert err_quota.category == "quota"
    assert "hạn mức trong ngày" in err_quota.message_vi
    assert "14:00" in (err_quota.user_action_required or "")

    # 429 rate limit
    err_rate = classify_client_error(429, "Rate limit exceeded. Please retry in 15s.")
    assert err_rate.category == "transient"
    assert "giới hạn tốc độ" in err_rate.message_vi

    # 5xx
    for code in (500, 502, 503, 504):
        err_5xx = classify_client_error(code, "Server Error")
        assert err_5xx.category == "transient"

    # 401/403
    err_auth = classify_client_error(401, "API key not valid")
    assert err_auth.category == "permanent"


def test_openai_classify_openai_error():
    # 402 quota
    err_402 = classify_openai_error(402, '{"error": {"message": "Insufficient credit"}}')
    assert err_402.category == "quota"

    # 429 daily quota
    daily_msg = '{"error": {"message": "Requests per day quota exceeded"}}'
    err_daily = classify_openai_error(429, daily_msg)
    assert err_daily.category == "quota"

    # 429 rate limit
    err_rate = classify_openai_error(429, '{"error": {"message": "Rate limit exceeded"}}')
    assert err_rate.category == "transient"

    # 500
    err_500 = classify_openai_error(500, "Internal Server Error")
    assert err_500.category == "transient"

    # 401
    err_401 = classify_openai_error(401, "Unauthorized")
    assert err_401.category == "permanent"
