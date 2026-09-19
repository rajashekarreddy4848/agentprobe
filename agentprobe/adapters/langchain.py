"""Adapter for LangChain / LangGraph: wrap tools so a graph's tool calls are recorded and
fault-injected. Use the wrapped tools anywhere you'd use the originals.

    tools = wrap_tools(probe, [lookup_order, issue_refund])
    agent = create_react_agent(model, tools)
"""
from langchain_core.tools import StructuredTool, ToolException


def wrap_tools(probe, tools):
    wrapped = []
    for tool in tools:
        if tool.func is None:
            raise TypeError(f"tool {tool.name!r} is async-only; async LangChain tools aren't supported yet")
        recorded = probe.tool(tool.func, name=tool.name)

        def guarded(*args, _recorded=recorded, **kwargs):
            try:
                return _recorded(*args, **kwargs)
            except Exception as e:
                # Surface failures to the model as a tool message instead of crashing the graph.
                raise ToolException(f"{type(e).__name__}: {e}") from e

        wrapped.append(
            StructuredTool.from_function(
                func=guarded,
                name=tool.name,
                description=tool.description,
                args_schema=tool.args_schema,
                handle_tool_error=True,
            )
        )
    return wrapped
