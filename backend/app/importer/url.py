"""Import chapter images from a URL (SPEC §6.1).

Only for sources the user is allowed to access. No login, captcha or anti-bot bypass:
401/403/429 or a page without images → stop and suggest folder import.
"""

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
import yaml
from selectolax.lexbor import LexborHTMLParser as HTMLParser

USER_AGENT = "ComicFilmStudio/0.1 (+local personal tool)"
MAX_HTML_BYTES = 10 * 1024 * 1024
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_REDIRECTS = 5
TIMEOUT = httpx.Timeout(20.0, connect=10.0)
PROFILES_DIR = Path(__file__).parent / "profiles"
DEFAULT_IMAGE_ATTRS = ["data-src", "data-original", "data-lazy-src", "data-srcset", "src", "srcset"]
JUNK_HINTS = ("logo", "icon", "avatar", "banner", "ads", "advert", "sprite", "loading", "emoji")


class UnsafeUrlError(ValueError):
    """URL is not allowed (scheme, private network, ...)."""


class FetchError(Exception):
    def __init__(self, message_vi: str, permanent: bool) -> None:
        super().__init__(message_vi)
        self.message_vi = message_vi
        self.permanent = permanent


# ---------------------------------------------------------------------------
# SSRF protection
# ---------------------------------------------------------------------------
def _ip_is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def validate_url(url: str, resolver: Callable[[str], list[str]] | None = None) -> str:
    """Return the normalized URL or raise UnsafeUrlError. Resolves DNS and rejects
    private / loopback / link-local / multicast targets (SSRF)."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError("Chỉ hỗ trợ đường dẫn http:// hoặc https://")
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("Đường dẫn thiếu tên miền")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("Không hỗ trợ đường dẫn có kèm tài khoản/mật khẩu")
    resolve = resolver or _resolve
    try:
        ips = resolve(host)
    except OSError as e:
        raise UnsafeUrlError(f"Không phân giải được tên miền {host}") from e
    if not ips:
        raise UnsafeUrlError(f"Không phân giải được tên miền {host}")
    for ip in ips:
        if not _ip_is_public(ip):
            raise UnsafeUrlError("Không cho phép truy cập địa chỉ mạng nội bộ / máy cục bộ")
    return parsed.geturl()


def _resolve(host: str) -> list[str]:
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        pass
    return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})


# ---------------------------------------------------------------------------
# Site profiles
# ---------------------------------------------------------------------------
@dataclass
class SiteProfile:
    domain: str
    image_selector: str = "img"
    image_attrs: list[str] = field(default_factory=lambda: list(DEFAULT_IMAGE_ATTRS))
    referer: bool = True


def load_profiles(directory: Path = PROFILES_DIR) -> list[SiteProfile]:
    out = []
    for f in sorted(directory.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        if not data.get("domain"):
            continue
        out.append(
            SiteProfile(
                domain=str(data["domain"]).lower(),
                image_selector=data.get("image_selector", "img"),
                image_attrs=list(data.get("image_attr") or DEFAULT_IMAGE_ATTRS),
                referer=bool(data.get("referer", True)),
            )
        )
    return out


def match_profile(url: str, profiles: list[SiteProfile]) -> SiteProfile | None:
    host = (urlparse(url).hostname or "").lower()
    for p in profiles:
        if host == p.domain or host.endswith("." + p.domain):
            return p
    return None


# ---------------------------------------------------------------------------
# HTML → image URLs
# ---------------------------------------------------------------------------
def _first_from_srcset(value: str) -> str:
    return value.split(",")[0].strip().split(" ")[0]


def extract_image_urls(html: str, base_url: str, profile: SiteProfile | None = None) -> list[str]:
    """Image URLs in DOM order, de-duplicated, junk filtered."""
    prof = profile or SiteProfile(domain="")
    tree = HTMLParser(html)
    urls: list[str] = []
    seen: set[str] = set()
    for node in tree.css(prof.image_selector):
        if node.tag != "img":
            # selector may target a container: take <img> inside it
            imgs = node.css("img")
        else:
            imgs = [node]
        for img in imgs:
            raw = None
            for attr in prof.image_attrs:
                v = (img.attributes.get(attr) or "").strip()
                if v and not v.startswith("data:"):
                    raw = _first_from_srcset(v) if "srcset" in attr else v
                    break
            if not raw:
                continue
            absolute = urljoin(base_url, raw)
            if urlparse(absolute).scheme not in ("http", "https"):
                continue
            lower = absolute.lower()
            path = urlparse(lower).path
            if path.endswith((".svg", ".gif", ".ico")):
                continue
            if profile is None and any(h in path.rsplit("/", 1)[-1] for h in JUNK_HINTS):
                continue
            if absolute not in seen:
                seen.add(absolute)
                urls.append(absolute)
    return urls


# ---------------------------------------------------------------------------
# HTTP with redirect re-validation and size caps
# ---------------------------------------------------------------------------
def _get(
    client: httpx.Client, url: str, max_bytes: int, headers: dict[str, str]
) -> tuple[str, bytes]:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        validate_url(current)
        with client.stream("GET", current, headers=headers, follow_redirects=False) as r:
            if r.is_redirect:
                loc = r.headers.get("location")
                if not loc:
                    raise FetchError("Trang chuyển hướng không hợp lệ", permanent=True)
                current = urljoin(current, loc)
                continue
            if r.status_code in (401, 403):
                raise FetchError(
                    f"Trang từ chối truy cập (HTTP {r.status_code}) — có thể cần đăng nhập "
                    "hoặc bị chặn. Hãy dùng 'Nhập từ thư mục'.",
                    permanent=True,
                )
            if r.status_code == 429:
                raise FetchError("Trang giới hạn số lần truy cập (HTTP 429)", permanent=False)
            if r.status_code >= 500:
                raise FetchError(f"Máy chủ lỗi (HTTP {r.status_code})", permanent=False)
            if r.status_code >= 400:
                raise FetchError(f"Không tải được (HTTP {r.status_code})", permanent=True)
            declared = int(r.headers.get("content-length") or 0)
            if declared > max_bytes:
                raise FetchError("Nội dung quá lớn", permanent=True)
            buf = bytearray()
            for chunk in r.iter_bytes():
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    raise FetchError("Nội dung quá lớn", permanent=True)
            return current, bytes(buf)
    raise FetchError("Quá nhiều lần chuyển hướng", permanent=True)


def make_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})


def fetch_chapter_html(client: httpx.Client, url: str) -> tuple[str, str]:
    final_url, body = _get(client, url, MAX_HTML_BYTES, {"Accept": "text/html,*/*"})
    return final_url, body.decode("utf-8", errors="replace")


def download_image(client: httpx.Client, url: str, referer: str | None, dest: Path) -> None:
    headers = {"Accept": "image/avif,image/webp,image/*,*/*"}
    if referer:
        headers["Referer"] = referer
    _, body = _get(client, url, MAX_IMAGE_BYTES, headers)
    dest.write_bytes(body)
