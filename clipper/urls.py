"""Post URL normalisation, so the same post can't be logged twice under different URLs."""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

# Hosts that only redirect to the real post URL.
SHORT_LINK_HOSTS = {"vm.tiktok.com", "vt.tiktok.com"}
# Hosts where the post ID is in the query string, so the query can't be dropped wholesale.
KEEP_QUERY_PARAMS = {
    "youtube.com": {"v"},
    "www.youtube.com": {"v"},
    "m.youtube.com": {"v"},
}


class UrlError(ValueError):
    pass


def expand_short_link(url: str, timeout: float = 10.0) -> str:
    """Follow redirects and return the final URL. Needs network."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.geturl()


def _strip(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise UrlError(f"not a web URL: {url!r}")
    host = parts.netloc.lower()
    keep = KEEP_QUERY_PARAMS.get(host, set())
    query = urlencode([(k, v[0]) for k, v in sorted(parse_qs(parts.query).items()) if k in keep])
    path = parts.path.rstrip("/")
    return urlunsplit(("https", host, path, query, ""))


def normalize_url(url: str) -> str:
    """Strip query params (except YouTube's ?v=), fragment and trailing slash;
    force https; lowercase the host; expand TikTok short links."""
    clean = _strip(url)
    host = urlsplit(clean).netloc
    if host in SHORT_LINK_HOSTS:
        try:
            expanded = expand_short_link(clean)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise UrlError(f"couldn't expand short link {url} ({e}); "
                           "open it in a browser and paste the full URL instead") from e
        clean = _strip(expanded)
        host = urlsplit(clean).netloc
        if host in SHORT_LINK_HOSTS or not re.search(r"/(video|photo)/\d+$", urlsplit(clean).path):
            raise UrlError(f"short link {url} expanded to {clean}, which doesn't look like "
                           "a post URL; paste the full URL instead")
    return clean
