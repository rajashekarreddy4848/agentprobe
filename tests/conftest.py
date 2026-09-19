"""Tests that call a paid API only run when you ask for them by name, so a plain `pytest` can
never spend money, even if a real key is sitting in your .env:

    pytest -m live_openai      # OpenAI (costs a few cents)
    pytest -m live             # Claude (costs a few cents)
"""
import re

import pytest

PAID_MARKERS = ("live", "live_openai")


def pytest_collection_modifyitems(config, items):
    asked_for = set(re.findall(r"\w+", config.getoption("markexpr") or ""))
    for item in items:
        for name in PAID_MARKERS:
            if item.get_closest_marker(name) and name not in asked_for:
                item.add_marker(pytest.mark.skip(reason=f"costs money: run with  pytest -m {name}"))
