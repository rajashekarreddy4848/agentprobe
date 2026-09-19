"""The playground web server. Local only: it listens on 127.0.0.1, refuses requests whose Host header isn't
this server (DNS rebinding), and refuses cross-site POSTs (they can't set the custom header). API keys are
used for one request and never stored or logged."""
import json
import threading
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .engine import PlaygroundError, run_playground
from .presets import PRESETS

STATIC = Path(__file__).parent / "static"
MAX_BODY = 300_000


def _ollama_models():
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as response:
            return [m["name"] for m in json.loads(response.read()).get("models", [])]
    except (OSError, ValueError):
        return []


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, content_type, status=200):
        payload = body if isinstance(body, bytes) else body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, obj, status=200):
        self._send(json.dumps(obj), "application/json", status)

    def _host_ok(self):
        port = self.server.server_address[1]
        return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def do_GET(self):
        if not self._host_ok():
            return self._json({"error": "forbidden"}, 403)
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._send((STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/presets":
            return self._json(PRESETS)
        if path == "/api/ollama-models":
            return self._json({"models": _ollama_models()})
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._host_ok() or self.headers.get("X-Agentprobe") != "1":
            return self._json({"error": "forbidden"}, 403)
        if urlparse(self.path).path != "/api/run":
            return self._json({"error": "not found"}, 404)
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._json({"error": "send JSON"}, 415)
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self.close_connection = True  # we won't read the body, so don't keep the connection
            return self._json({"error": "request too large"}, 413)
        try:
            request = json.loads(self.rfile.read(length) or b"{}")
            self._json(run_playground(request))
        except PlaygroundError as e:
            self._json({"error": str(e)}, 400)
        except (ValueError, TypeError, KeyError, AttributeError):
            self._json({"error": "That request wasn't valid. Check the fields and try again."}, 400)
        except Exception:
            self._json({"error": "Something went wrong running the test."}, 500)

    def log_message(self, *args):
        pass


def serve(port=8788, open_browser=True):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"agentprobe playground: {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
