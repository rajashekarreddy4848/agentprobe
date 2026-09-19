"""Tests against a REAL local HTTP API + SQLite database (examples/api_server.py).
Skipped automatically when the server isn't running, so CI stays green without any setup.
Run locally with:
    uvicorn examples.api_server:app --port 8000   (separate terminal)
    pytest -m live_api -v
"""
import urllib.request

import pytest


def _server_running():
    """True only if the demo API answers, not merely if something is listening on port 8000."""
    try:
        with urllib.request.urlopen("http://localhost:8000/orders/A123", timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


live_api = pytest.mark.skipif(
    not _server_running(),
    reason="needs `uvicorn examples.api_server:app --port 8000` running locally",
)


@live_api
@pytest.mark.live_api
def test_lookup_and_refund_over_real_http(probe):
    from examples.http_tools import TOOLS

    tools = probe.wrap(TOOLS)
    order = tools["lookup_order"](order_id="A123")
    assert order["status"] == "delivered"
    tools["issue_refund"](order_id="A123", amount=order["amount"])

    (probe.trajectory
        .called_before("lookup_order", "issue_refund")
        .called_with("issue_refund", order_id="A123", amount=49.99))


@live_api
@pytest.mark.live_api
def test_lookup_missing_order_raises_over_real_http():
    from examples.http_tools import lookup_order

    with pytest.raises(Exception):
        lookup_order(order_id="NOPE")


@live_api
@pytest.mark.live_api
@pytest.mark.fault("lookup_order", "timeout")
def test_fault_injection_works_over_real_http_tool(probe):
    """agentprobe's synthetic fault fires before the real network call is made."""
    from examples.http_tools import TOOLS

    tools = probe.wrap(TOOLS)
    with pytest.raises(TimeoutError):
        tools["lookup_order"](order_id="A123")

    probe.trajectory.called("lookup_order")
