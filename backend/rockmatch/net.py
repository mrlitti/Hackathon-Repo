"""Small HTTPS helper with certificate verification via the OS trust store."""
from __future__ import annotations

import html
import json
import re
import ssl
import urllib.parse
import urllib.request

try:
    import truststore
    SSL_CTX = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
except ImportError:  # pragma: no cover
    try:
        import certifi
        SSL_CTX = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        SSL_CTX = ssl.create_default_context()

USER_AGENT = "RockMatch-SpaceApps/1.0 (educational hackathon project)"


def http_get(url: str, timeout: float = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
        return r.read()


def http_json(url: str, timeout: float = 15):
    return json.loads(http_get(url, timeout))


def dir_listing(url: str, timeout: float = 15) -> list[str]:
    """File names in an Apache/IIS directory listing."""
    if not url.endswith("/"):
        url += "/"
    page = http_get(url, timeout).decode("utf-8", "replace")
    base = urllib.parse.urlparse(url).path
    names = set()
    for href in re.findall(r'href="([^"]+)"', page, flags=re.I):
        path = urllib.parse.urlparse(urllib.parse.urljoin(url, html.unescape(href))).path
        if path.startswith(base) and path != base:
            name = urllib.parse.unquote(path[len(base):])
            if name and "/" not in name:
                names.add(name)
    return sorted(names)
