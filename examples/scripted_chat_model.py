"""A deterministic stand-in for an LLM, for testing agent graphs without a model.
It replays a fixed script of replies, so a test can drive a real LangGraph graph
(tool node, error handling, message flow) with zero randomness.

    ScriptedChatModel(script=[tool_call("lookup_order", order_id="A123"), AIMessage("Done")])
"""
import itertools

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

_ids = itertools.count(1)


def tool_call(name, **args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{next(_ids)}"}])


class ScriptedChatModel(BaseChatModel):
    script: list
    cursor: int = 0

    @property
    def _llm_type(self):
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        reply = self.script[min(self.cursor, len(self.script) - 1)]
        self.cursor += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])
