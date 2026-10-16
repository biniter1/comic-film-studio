import pytest

from app.importer.url import UnsafeUrlError, validate_url


def public(_host):
    return ["93.184.216.34"]


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://localhost/x",
        "http://10.0.0.1/x",
        "http://192.168.1.10/x",
        "http://172.16.5.4/x",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/x",
        "http://0.0.0.0/x",
        "file:///etc/passwd",
        "ftp://example.com/x",
        "http://user:pass@example.com/x",
        "javascript:alert(1)",
    ],
)
def test_blocked_urls(url):
    with pytest.raises(UnsafeUrlError):
        validate_url(url)


def test_domain_resolving_to_private_ip_is_blocked():
    with pytest.raises(UnsafeUrlError):
        validate_url("https://evil.example/ch1", resolver=lambda h: ["10.1.2.3"])


def test_any_private_ip_among_many_is_blocked():
    with pytest.raises(UnsafeUrlError):
        validate_url("https://mixed.example/", resolver=lambda h: ["93.184.216.34", "127.0.0.1"])


def test_ipv4_mapped_ipv6_loopback_blocked():
    with pytest.raises(UnsafeUrlError):
        validate_url("http://[::ffff:127.0.0.1]/")


def test_public_url_ok():
    assert validate_url("https://truyen.example/ch-1", resolver=public).startswith("https://")
