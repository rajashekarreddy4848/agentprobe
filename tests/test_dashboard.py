import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from agentprobe import cli, dashboard
from agentprobe.store import Store

CALLS = [{"step": 1, "tool": "lookup_order", "args": {"order_id": "'A1'"}, "result": "'ok'",
          "error": None, "fault": None, "duration_ms": 1.0}]


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "runs.db"
    store = Store(path)
    for label, outcome in (("one", "PASSED"), ("two", "FAILED")):
        run_id = store.start_run(label)
        store.add_result(run_id, "tests/t.py::test_a", outcome, 12.0, CALLS)
        store.add_result(run_id, "tests/t.py::test_b", "XFAIL (bug caught)", 3.0)
        store.finish_run(run_id)
    store.close()
    return path


def test_build_data_summarizes_runs_tests_and_trend(db):
    store = Store(db)
    data = dashboard.build_data(store)
    store.close()

    assert data["summary"]["runs"] == 2 and data["summary"]["tests"] == 2
    assert data["summary"]["flaky"] == 1  # test_a passed once and failed once
    assert [p["run_id"] for p in data["trend"]] == [1, 2]  # oldest first, for the chart
    assert data["runs"][0]["id"] == 2  # newest first, for the table
    assert "run_details" not in data


def test_export_writes_a_self_contained_static_site(db, tmp_path):
    out = dashboard.export(db, tmp_path / "site")

    assert "agentprobe dashboard" in (out / "index.html").read_text()
    payload = (out / "data.js").read_text()
    data = json.loads(payload.removeprefix("window.AGENTPROBE_DATA = ").removesuffix(";\n"))
    assert data["run_details"]["1"]["results"][0]["calls"][0]["tool"] == "lookup_order"
    assert "tests/t.py::test_a" in data["test_history"]


def test_page_never_builds_html_from_strings():
    """Stored data holds hostile text on purpose (prompt injections), so the page must only ever
    use textContent, never HTML strings."""
    html = (dashboard.STATIC / "index.html").read_text()

    for banned in ("innerHTML", "insertAdjacentHTML", "document.write", "outerHTML"):
        assert banned not in html


@pytest.fixture
def server(db):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), dashboard._handler(str(db)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def fetch(url):
    with urllib.request.urlopen(url) as response:
        return response.status, response.read().decode()


def test_server_serves_the_page_and_the_json_api(server):
    status, body = fetch(server + "/")
    assert status == 200 and "agentprobe dashboard" in body

    assert json.loads(fetch(server + "/api/data")[1])["summary"]["runs"] == 2
    assert json.loads(fetch(server + "/api/run/1")[1])["results"][0]["nodeid"] == "tests/t.py::test_a"
    assert len(json.loads(fetch(server + "/api/test?nodeid=tests/t.py::test_a")[1])) == 2
    assert fetch(server + "/data.js") == (200, "")  # empty in server mode, so the page fetches the API


@pytest.mark.parametrize("path", ["/api/run/999", "/api/run/abc", "/nope"])
def test_server_returns_404_for_unknown_things(server, path):
    with pytest.raises(urllib.error.HTTPError) as error:
        fetch(server + path)

    assert error.value.code == 404


def test_serve_explains_a_missing_store(tmp_path):
    with pytest.raises(SystemExit, match="pytest --agentprobe-store"):
        dashboard.serve(tmp_path / "missing.db")


def test_cli_export(db, tmp_path, capsys):
    cli.main(["export", str(db), str(tmp_path / "out")])

    assert (tmp_path / "out" / "index.html").exists()
    assert "wrote" in capsys.readouterr().out


def test_export_can_link_back_to_the_site(db, tmp_path):
    out = dashboard.export(db, tmp_path / "site", home_url="../")

    data = json.loads((out / "data.js").read_text().removeprefix("window.AGENTPROBE_DATA = ").removesuffix(";\n"))
    assert data["home_url"] == "../"


def test_no_back_link_unless_a_home_url_is_given(db, tmp_path):
    out = dashboard.export(db, tmp_path / "site")

    assert "home_url" not in (out / "data.js").read_text()


def test_cli_export_home_option(db, tmp_path):
    cli.main(["export", str(db), str(tmp_path / "out"), "--home", "https://example.com/"])

    assert '"home_url": "https://example.com/"' in (tmp_path / "out" / "data.js").read_text()
