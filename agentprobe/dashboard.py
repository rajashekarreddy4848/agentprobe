"""Dashboard: a local web app over the run store (history, flaky and slow tests, trends).

    agentprobe dashboard runs.db          # serve at http://127.0.0.1:8787
    agentprobe export runs.db site/       # static copy you can host anywhere (e.g. GitHub Pages)

Stored data includes hostile text on purpose (prompt-injection payloads), so the page renders
everything with textContent, and the server only listens on localhost.
"""
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .store import Store

STATIC = Path(__file__).parent / "dashboard_static"


def build_data(store, details=False):
    """Everything the dashboard shows. With details=True, also every run's trajectories and every
    test's history, so the result can be exported as a static site."""
    runs = store.runs()
    tests = store.tests()
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": {
            "runs": len(runs),
            "tests": len(tests),
            "flaky": sum(1 for t in tests if t["flaky"]),
            "latest": runs[0] if runs else None,
        },
        "trend": [
            {"run_id": r["id"], "label": r["label"], "started_at": r["started_at"],
             "pass_rate": r["pass_rate"], "total": r["total"]}
            for r in reversed(runs)
        ],
        "runs": runs,
        "tests": tests,
        "tools": store.tools(),
    }
    if details:
        data["run_details"] = {str(r["id"]): store.run(r["id"]) for r in runs}
        data["test_history"] = {t["nodeid"]: store.test_history(t["nodeid"]) for t in tests}
    return data


def export(db_path, out_dir):
    """Write a self-contained static dashboard (index.html + data.js) to out_dir."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    store = Store(db_path)
    try:
        data = build_data(store, details=True)
    finally:
        store.close()
    (out / "index.html").write_text((STATIC / "index.html").read_text())
    (out / "data.js").write_text("window.AGENTPROBE_DATA = " + json.dumps(data) + ";\n")
    return out


def _handler(db_path):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, body, content_type, status=200):
            payload = body if isinstance(body, bytes) else body.encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, obj, status=200):
            self._send(json.dumps(obj), "application/json", status)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                return self._send((STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            if url.path == "/data.js":  # static-export data; empty in server mode
                return self._send("", "application/javascript")
            store = Store(db_path)
            try:
                if url.path == "/api/data":
                    return self._json(build_data(store))
                if url.path.startswith("/api/run/"):
                    run_id = url.path.rsplit("/", 1)[-1]
                    run = store.run(int(run_id)) if run_id.isdigit() else None
                    return self._json(run, 200 if run else 404)
                if url.path == "/api/test":
                    nodeid = parse_qs(url.query).get("nodeid", [""])[0]
                    return self._json(store.test_history(nodeid))
            finally:
                store.close()
            self._send("not found", "text/plain", 404)

        def log_message(self, *args):
            pass

    return Handler


def serve(db_path, port=8787):
    if not Path(db_path).exists():
        raise SystemExit(f"No run store at {db_path}. Create one with: pytest --agentprobe-store={db_path}")
    server = ThreadingHTTPServer(("127.0.0.1", port), _handler(db_path))
    print(f"agentprobe dashboard: http://127.0.0.1:{server.server_address[1]}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
