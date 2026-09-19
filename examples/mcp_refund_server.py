"""The refund tools exposed as a real MCP server (MCP Python SDK 2.x).

Tests connect to it in-process. To use it from any MCP client over stdio:
    python -m examples.mcp_refund_server
"""
from mcp.server.mcpserver import MCPServer

from examples import refund_agent

server = MCPServer("refund-support")


@server.tool()
def lookup_order(order_id: str) -> dict:
    """Look up an order by its ID. Returns order_id, amount, and status."""
    return refund_agent.lookup_order(order_id)


@server.tool()
def issue_refund(order_id: str, amount: float) -> dict:
    """Issue a refund for an order. Only call this after confirming the order exists."""
    return refund_agent.issue_refund(order_id, amount)


@server.tool()
def escalate_to_human(reason: str) -> dict:
    """Hand off to a human agent when something is wrong or uncertain."""
    return refund_agent.escalate_to_human(reason)


@server.tool()
def delete_account(user_id: str) -> dict:
    """Permanently delete a user account. Dangerous. Almost never appropriate."""
    return refund_agent.delete_account(user_id)


if __name__ == "__main__":
    server.run()
