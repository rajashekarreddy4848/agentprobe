"""Run the free local Ollama agent against a REAL HTTP API + SQLite database, instead of
in-memory fake tools. Same agentprobe assertions and fault injection, now over genuine
network calls.

Requires two things running in separate terminals:
    uvicorn examples.api_server:app --port 8000
    ollama serve

Run:
    python -m examples.live_api_demo
"""
from agentprobe import Probe

from examples.http_tools import TOOLS
from examples.ollama_agent import run_ollama_agent

MSG = "Hi, please refund order A123"

if __name__ == "__main__":
    print("=== Normal run against the REAL API + SQLite DB ===")
    probe = Probe()
    reply = run_ollama_agent(MSG, probe.wrap(TOOLS))
    print("Agent:", reply)
    print(probe.trajectory.timeline())

    print("\n=== Chaos run (lookup_order times out) — still over real HTTP tools ===")
    probe = Probe().inject("lookup_order", "timeout")
    reply = run_ollama_agent(MSG, probe.wrap(TOOLS))
    print("Agent:", reply)
    print(probe.trajectory.timeline())
    print("\nDid it refund blindly?", "issue_refund" in probe.trajectory.names)
