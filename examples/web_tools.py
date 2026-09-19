"""Tools for a web-reading agent. `fetch_page` makes a REAL HTTP request; `send_email` and
`delete_file` are SIMULATED (they only return a receipt), so nothing dangerous can happen
even when an agent is tricked into calling them.
"""
import urllib.request
from html.parser import HTMLParser

MAX_CHARS = 4000


class _TextExtractor(HTMLParser):
    """Naive text extraction, like many real agent pipelines: it keeps text inside hidden
    elements (display:none), which is exactly how hidden prompt injections reach the model."""

    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def fetch_page(url):
    if not url.startswith(("http://", "https://")):
        raise ValueError("only http(s) URLs are allowed")
    request = urllib.request.Request(url, headers={"User-Agent": "agentprobe-demo/0.1"})
    with urllib.request.urlopen(request, timeout=5) as response:
        html = response.read(200_000).decode("utf-8", errors="replace")
    extractor = _TextExtractor()
    extractor.feed(html)
    return " ".join(extractor.parts)[:MAX_CHARS]


def send_email(to, body):
    return {"status": "sent (simulated)", "to": to}


def delete_file(path):
    return {"deleted": path, "note": "simulated"}


TOOLS = {f.__name__: f for f in (fetch_page, send_email, delete_file)}
