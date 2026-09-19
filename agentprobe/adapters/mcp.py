"""Adapter for the MCP Python SDK: record and fault-inject every `call_tool`.

    async with Client(server) as client:
        probed = ProbedMCPClient(probe, client)
        await my_agent(message, probed)      # everything except call_tool passes through

Faults behave like they do for plain functions: `timeout` raises, `malformed`/`empty` replace the
result, `prompt_injection` appends text to the real result. A tool that the SERVER reports as
failed (is_error=True) is recorded as an error, and the agent still receives the real result.
"""
import json

from mcp.types import CallToolResult, TextContent


class _ServerReportedError(Exception):
    pass


def _text(result):
    return "\n".join(c.text for c in result.content if getattr(c, "text", None) is not None)


def _simplify(result):
    text = _text(result)
    try:
        return json.loads(text)
    except ValueError:
        return text


class ProbedMCPClient:
    def __init__(self, probe, client):
        self._probe = probe
        self._client = client

    def __getattr__(self, name):
        return getattr(self._client, name)

    async def call_tool(self, name, arguments=None, *args, **kwargs):
        raw = {}

        async def real(**tool_args):
            result = await self._client.call_tool(name, tool_args, *args, **kwargs)
            raw["result"] = result
            if result.is_error:
                raise _ServerReportedError(_text(result))
            return _simplify(result)

        try:
            out = await self._probe.wrap_async(real, name=name)(**(arguments or {}))
        except _ServerReportedError:
            return raw["result"]
        result = raw.get("result")
        if result is not None and out == _simplify(result):
            return result
        text = out if isinstance(out, str) else json.dumps(out)
        return CallToolResult(content=[TextContent(type="text", text=text)])
