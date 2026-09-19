"""Probe: wraps an agent's tools to record every call and inject faults."""
import functools
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .assertions import Trajectory
from .faults import make_fault


@dataclass
class ToolCall:
    step: int
    tool: str
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    result: Any = None
    error: Optional[str] = None
    fault: Optional[str] = None
    duration_ms: float = 0.0


class Probe:
    def __init__(self):
        self.calls = []
        self._faults = {}

    def inject(self, tool, fault, **kwargs):
        self._faults.setdefault(tool, []).append(make_fault(fault, **kwargs))
        return self

    def wrap(self, tools):
        """Wrap a dict of {name: callable} (or a single callable)."""
        if callable(tools):
            return self._wrap_one(tools.__name__, tools)
        return {name: self._wrap_one(name, fn) for name, fn in tools.items()}

    def tool(self, fn=None, *, name=None):
        """Decorator form: @probe.tool"""
        def deco(f):
            return self._wrap_one(name or f.__name__, f)
        return deco(fn) if fn else deco

    def wrap_async(self, fn, *, name=None):
        """Wrap an `async def` tool. Same recording and faults as the sync version."""
        return self._wrap_one_async(name or fn.__name__, fn)

    @property
    def trajectory(self):
        return Trajectory(self.calls)

    def _active_fault(self, tool):
        for f in self._faults.get(tool, []):
            if f.should_fire():
                return f
        return None

    def _begin(self, name, args, kwargs):
        call = ToolCall(step=len(self.calls) + 1, tool=name, args=args, kwargs=kwargs)
        self.calls.append(call)
        fault = self._active_fault(name)
        if fault:
            call.fault = fault.name
            fault.fired += 1
        return call, fault, time.perf_counter()

    def _wrap_one(self, name, fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            call, fault, start = self._begin(name, args, kwargs)
            try:
                result = fault.apply(fn, args, kwargs) if fault else fn(*args, **kwargs)
                call.result = result
                return result
            except Exception as e:
                call.error = f"{type(e).__name__}: {e}"
                raise
            finally:
                call.duration_ms = (time.perf_counter() - start) * 1000
        return wrapper

    def _wrap_one_async(self, name, fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            call, fault, start = self._begin(name, args, kwargs)
            try:
                if fault and fault.wraps_result:
                    real = await fn(*args, **kwargs)
                    result = fault.apply(lambda *a, **k: real, args, kwargs)
                elif fault:
                    result = fault.apply(fn, args, kwargs)
                else:
                    result = await fn(*args, **kwargs)
                call.result = result
                return result
            except Exception as e:
                call.error = f"{type(e).__name__}: {e}"
                raise
            finally:
                call.duration_ms = (time.perf_counter() - start) * 1000
        return wrapper
