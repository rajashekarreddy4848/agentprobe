"""Tool implementations that call the REAL local API (examples/api_server.py) over HTTP,
instead of the in-memory functions in refund_agent.py. Same names/signatures, so agentprobe
wraps them identically — proving it works against real network calls and a real database,
not just mocked Python functions.

Requires the API server running:
    uvicorn examples.api_server:app --port 8000
"""
import requests

BASE_URL = "http://localhost:8000"


def lookup_order(order_id: str):
    resp = requests.get(f"{BASE_URL}/orders/{order_id}", timeout=5)
    resp.raise_for_status()
    return resp.json()


def issue_refund(order_id: str, amount: float):
    resp = requests.post(f"{BASE_URL}/refunds", json={"order_id": order_id, "amount": amount}, timeout=5)
    resp.raise_for_status()
    return resp.json()


def escalate_to_human(reason: str):
    resp = requests.post(f"{BASE_URL}/escalations", json={"reason": reason}, timeout=5)
    resp.raise_for_status()
    return resp.json()


def delete_account(user_id: str):
    resp = requests.delete(f"{BASE_URL}/accounts/{user_id}", timeout=5)
    resp.raise_for_status()
    return resp.json()


TOOLS = {f.__name__: f for f in (lookup_order, issue_refund, escalate_to_human, delete_account)}
