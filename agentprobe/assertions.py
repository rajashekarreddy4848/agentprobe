"""Trajectory assertions: test what the agent DID, not just what it said."""


class TrajectoryAssertionError(AssertionError):
    pass


class Trajectory:
    def __init__(self, calls):
        self.calls = list(calls)

    @property
    def names(self):
        return [c.tool for c in self.calls]

    def timeline(self):
        if not self.calls:
            return "  (no tool calls)"
        lines = []
        for c in self.calls:
            args = ", ".join([repr(a) for a in c.args] + [f"{k}={v!r}" for k, v in c.kwargs.items()])
            outcome = f"ERROR {c.error}" if c.error else f"-> {c.result!r}"
            fault = f"  [fault: {c.fault}]" if c.fault else ""
            lines.append(f"  {c.step}. {c.tool}({args}) {outcome}{fault}")
        return "\n".join(lines)

    def _fail(self, message):
        raise TrajectoryAssertionError(f"{message}\n\nTrajectory:\n{self.timeline()}")

    # ---- assertions (all chainable) ----

    def called(self, tool, times=None):
        count = self.names.count(tool)
        if count == 0:
            self._fail(f"Expected '{tool}' to be called, but it never was.")
        if times is not None and count != times:
            self._fail(f"Expected '{tool}' to be called {times}x, got {count}x.")
        return self

    def never_called(self, *tools):
        for tool in tools:
            if tool in self.names:
                self._fail(f"Expected '{tool}' to NEVER be called, but it was.")
        return self

    def called_before(self, first, then):
        """Every call to `then` must come after at least one call to `first`."""
        seen_first = False
        for c in self.calls:
            if c.tool == first:
                seen_first = True
            elif c.tool == then and not seen_first:
                self._fail(f"'{then}' was called before '{first}'.")
        return self

    def called_after_success(self, prerequisite, tool):
        """Every call to `tool` must follow a SUCCESSFUL call to `prerequisite`.
        Key chaos-test check: the agent must not act on data it never got."""
        ok = False
        for c in self.calls:
            if c.tool == prerequisite and c.error is None and c.fault is None:
                ok = True
            elif c.tool == tool and not ok:
                self._fail(f"'{tool}' was called without a successful '{prerequisite}' first.")
        return self

    def called_with(self, tool, **expected):
        for c in self.calls:
            if c.tool == tool and all(c.kwargs.get(k) == v for k, v in expected.items()):
                return self
        self._fail(f"No call to '{tool}' matched {expected}.")

    def max_steps(self, n):
        if len(self.calls) > n:
            self._fail(f"Expected at most {n} tool calls, got {len(self.calls)}.")
        return self
