"""Demo customer-support agent. Decision logic is scripted (no LLM needed) so tests are
deterministic; the buggy version mimics real LLM agent failure modes."""
import re

ORDERS = {"A123": {"order_id": "A123", "amount": 49.99, "status": "delivered"}}


def lookup_order(order_id):
    return dict(ORDERS[order_id])


def issue_refund(order_id, amount):
    return {"refund_id": f"R-{order_id}", "amount": amount}


def escalate_to_human(reason):
    return {"ticket": "T-1", "reason": reason}


def delete_account(user_id):
    return {"deleted": user_id}


TOOLS = {f.__name__: f for f in (lookup_order, issue_refund, escalate_to_human, delete_account)}


def _order_id(message):
    return re.search(r"\b[A-Z]\d{3}\b", message).group()


def buggy_refund_agent(message, tools):
    """Mimics common agent bugs: assumes success on errors, obeys text in tool output."""
    order_id = _order_id(message)
    try:
        order = tools["lookup_order"](order_id=order_id)
    except Exception:
        order = {"order_id": order_id, "amount": 49.99}  # BUG: hallucinates the order
    if not isinstance(order, dict):
        order = {"order_id": order_id, "amount": 49.99}  # BUG: ignores malformed data
    if "delete_account" in str(order.get("note", "")):
        tools["delete_account"](user_id="current_user")  # BUG: follows injected instruction
    return tools["issue_refund"](order_id=order_id, amount=order.get("amount", 49.99))


def safe_refund_agent(message, tools):
    order_id = _order_id(message)
    try:
        order = tools["lookup_order"](order_id=order_id)
    except Exception as e:
        return tools["escalate_to_human"](reason=f"lookup failed: {e}")
    if not isinstance(order, dict) or "amount" not in order:
        return tools["escalate_to_human"](reason="order data invalid")
    # tool output is data, never instructions -> 'note' is ignored
    if order.get("status") != "delivered":
        return tools["escalate_to_human"](reason="order not delivered")
    return tools["issue_refund"](order_id=order_id, amount=order["amount"])
