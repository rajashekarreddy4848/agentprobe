"""Repeat a scenario and measure a pass rate. LLM agents are not deterministic, so one green
run proves little: run it N times and require e.g. 9 out of 10.

    def scenario(probe):
        agent(MSG, probe.wrap(TOOLS))
        probe.trajectory.never_called("delete_account")

    run_repeated(scenario, runs=10, faults=[("lookup_order", "prompt_injection")]).require(0.9)
"""
from dataclasses import dataclass, field

from .recorder import Probe


@dataclass
class RepeatResult:
    runs: int
    passes: int = 0
    failures: list = field(default_factory=list)  # (run index, exception, probe)
    probes: list = field(default_factory=list)

    @property
    def pass_rate(self):
        return self.passes / self.runs

    def require(self, min_pass_rate):
        if self.pass_rate + 1e-9 >= min_pass_rate:
            return self
        index, error, probe = self.failures[0]
        raise AssertionError(
            f"pass rate {self.pass_rate:.0%} ({self.passes}/{self.runs}) is below the required "
            f"{min_pass_rate:.0%}.\nFirst failure (run {index + 1}): {error}\n\n"
            f"Trajectory:\n{probe.trajectory.timeline()}"
        )


def run_repeated(scenario, runs=10, faults=()):
    """Call `scenario(probe)` `runs` times, each with a fresh Probe. `faults` is a list of
    (tool, kind) or (tool, kind, kwargs). Any exception (failed assertion or agent crash) counts
    as a failed run. Returns a RepeatResult; call `.require(rate)` to enforce a pass rate."""
    if runs < 1:
        raise ValueError("runs must be at least 1")
    result = RepeatResult(runs=runs)
    for index in range(runs):
        probe = Probe()
        for tool, kind, *rest in faults:
            probe.inject(tool, kind, **(rest[0] if rest else {}))
        try:
            scenario(probe)
            result.passes += 1
        except Exception as error:
            result.failures.append((index, error, probe))
        result.probes.append(probe)
    return result
