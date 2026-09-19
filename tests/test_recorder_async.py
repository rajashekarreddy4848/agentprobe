import asyncio

import pytest

from agentprobe import Probe


async def lookup(order_id):
    return {"order_id": order_id, "amount": 49.99}


def run(coro):
    return asyncio.run(coro)


def test_async_tool_is_recorded():
    probe = Probe()
    result = run(probe.wrap_async(lookup)(order_id="A123"))

    assert result["amount"] == 49.99
    probe.trajectory.called("lookup", times=1).called_with("lookup", order_id="A123")


def test_async_tool_errors_are_recorded_and_reraised():
    async def boom():
        raise ValueError("kaput")

    probe = Probe()
    with pytest.raises(ValueError):
        run(probe.wrap_async(boom)())

    assert probe.calls[0].error == "ValueError: kaput"


def test_async_timeout_fault_raises():
    probe = Probe().inject("lookup", "timeout")
    with pytest.raises(TimeoutError):
        run(probe.wrap_async(lookup)(order_id="A123"))

    assert probe.calls[0].fault == "timeout"


def test_async_prompt_injection_wraps_the_real_result():
    probe = Probe().inject("lookup", "prompt_injection")
    result = run(probe.wrap_async(lookup)(order_id="A123"))

    assert result["amount"] == 49.99
    assert "delete_account" in result["note"]
