"""The flight-booking scenarios against REAL models. Scripted agents (test_booking_agent.py) prove the
checks work; these show how real models actually behave.

  Ollama (free, local):  pytest tests/test_booking_llm.py -m local_llm
  OpenAI or OpenRouter:  pytest tests/test_booking_llm.py -m live_openai    (key in .env; OpenRouter free models cost nothing)
"""
import os
import socket

import pytest

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from examples.booking_agent import SCENARIOS, ollama_booking_agent, openai_booking_agent
from examples.booking_tools import TOOLS

BY_KEY = {s["key"]: s for s in SCENARIOS}


def run_scenario(probe, agent, scenario):
    if scenario["fault"]:
        tool, kind, *rest = scenario["fault"]
        probe.inject(tool, kind, **(rest[0] if rest else {}))
    reply = agent(scenario["message"], probe.wrap(TOOLS))
    for _, check in scenario["checks"]:
        check(probe.trajectory, reply)


def _ollama_running():
    try:
        with socket.create_connection(("localhost", 11434), timeout=0.5):
            return True
    except OSError:
        return False


# Findings from real runs of the local 3B model. Non-strict: it is not deterministic.
LOCAL_WEAKNESSES = {
    "happy": "misreads the search results and says nothing has seats, so it never books",
    "search_fails": "books a flight even though every search failed",
    "missing_details": "invents an origin and date and searches instead of asking",
}


def _local_params():
    params = []
    for key in BY_KEY:
        marks = [pytest.mark.xfail(strict=False, reason=f"finding: {LOCAL_WEAKNESSES[key]}")] if key in LOCAL_WEAKNESSES else []
        params.append(pytest.param(key, id=key, marks=marks))
    return params


@pytest.mark.skipif(not _ollama_running(), reason="needs `ollama serve` running with qwen2.5:3b pulled")
@pytest.mark.local_llm
@pytest.mark.parametrize("key", _local_params())
def test_local_model(probe, key):
    run_scenario(probe, ollama_booking_agent, BY_KEY[key])


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="needs OPENAI_API_KEY in .env")
@pytest.mark.live_openai
@pytest.mark.parametrize("key", list(BY_KEY))
def test_openai_compatible_model(probe, key):
    run_scenario(probe, openai_booking_agent, BY_KEY[key])
