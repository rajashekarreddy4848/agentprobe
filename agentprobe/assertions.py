"""Trajectory assertions: test what the agent DID, not just what it said."""
from . import claims as _claims


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

    # ---- says vs. does: compare the reply with the actions ----

    def claims_backed_by_actions(self, reply, claims):
        """Every action the reply CLAIMS was done must have a successful call.
        `claims` maps a tool name to a regex (or list of regexes) that a claim sentence matches, e.g.
        {"issue_refund": r"refund.*(issued|processed)"}. Catches hallucinated success."""
        for tool, sentence in _claims.claimed_actions(reply, claims).items():
            calls = [c for c in self.calls if c.tool == tool]
            if any(c.error is None for c in calls):
                continue
            state = "was never called" if not calls else "was called but every call failed"
            self._fail(f"The reply claims {tool!r} happened, but it {state}.\nReply said: {sentence!r}")
        return self

    def actions_disclosed_in_reply(self, reply, disclosures):
        """Every action that WAS done must be mentioned in the reply. `disclosures` maps a tool name
        to a regex (or list) that a mention matches, e.g. {"delete_account": r"delet|remov"}.
        Catches silent side effects."""
        for tool, spec in disclosures.items():
            if any(c.tool == tool and c.error is None for c in self.calls) and not _claims.mentions(reply, spec):
                self._fail(f"The agent did {tool!r}, but the reply never mentions it.\nReply said: {reply!r}")
        return self
