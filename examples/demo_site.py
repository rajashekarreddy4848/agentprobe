"""Serve docs/demo/ over real local HTTP, so web-agent tests and recordings fetch pages
across a genuine network connection instead of reading files.

    with serve() as base_url:
        fetch_page(f"{base_url}/article.html")
"""
import contextlib
import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent.parent / "docs" / "demo"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@contextlib.contextmanager
def serve(port=0, directory=DEMO_DIR):
    handler = functools.partial(_QuietHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
