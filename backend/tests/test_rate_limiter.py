from unittest.mock import patch

from app.providers.rate_limiter import RateLimiter


def test_rate_limiter_spacing():
    limiter = RateLimiter()
    sleeps: list[float] = []

    # Mock time.monotonic to control time flow
    fake_time = 1000.0

    def mock_time():
        return fake_time

    with patch("time.monotonic", side_effect=mock_time):
        # First call succeeds immediately
        limiter.acquire(rpm=4, sleep_fn=sleeps.append)
        assert len(sleeps) == 0

        # Second call immediately should sleep because min_spacing is 60/4 = 15s
        # Notice that in acquire, while True loops until wait_time <= 0.001.
        # To avoid infinite loop, sleep_fn should advance fake_time!
        def mock_sleep(duration: float):
            nonlocal fake_time
            sleeps.append(duration)
            fake_time += duration

        limiter.acquire(rpm=4, sleep_fn=mock_sleep)
        assert len(sleeps) > 0
        assert sum(sleeps) >= 14.9


def test_rate_limiter_reset():
    limiter = RateLimiter()
    limiter.acquire(rpm=4, sleep_fn=lambda _: None)
    assert len(limiter._timestamps) == 1
    limiter.reset()
    assert len(limiter._timestamps) == 0
