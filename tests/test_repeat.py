import pytest

from agentprobe import run_repeated


def make_scenario(fail_on):
    calls = {"n": 0}

    def scenario(probe):
        calls["n"] += 1
        if calls["n"] in fail_on:
            raise AssertionError(f"run {calls['n']} misbehaved")

    return scenario


def test_counts_passes_and_failures():
    result = run_repeated(make_scenario(fail_on={2, 5}), runs=10)

    assert (result.runs, result.passes, len(result.failures)) == (10, 8, 2)
    assert result.pass_rate == 0.8


def test_require_passes_at_or_above_the_threshold():
    result = run_repeated(make_scenario(fail_on={4}), runs=10)

    assert result.require(0.9) is result


def test_require_raises_below_the_threshold_with_the_first_failure():
    result = run_repeated(make_scenario(fail_on={3, 4, 5}), runs=10)

    with pytest.raises(AssertionError, match=r"(?s)pass rate 70% \(7/10\).*run 3 misbehaved"):
        result.require(0.9)


def test_each_run_gets_a_fresh_probe_with_the_faults_injected():
    seen = []

    def lookup():
        return "real"

    def scenario(probe):
        seen.append(probe)
        with pytest.raises(TimeoutError):
            probe.wrap(lookup)()

    run_repeated(scenario, runs=3, faults=[("lookup", "timeout")])

    assert len({id(p) for p in seen}) == 3
    assert all(len(p.calls) == 1 and p.calls[0].fault == "timeout" for p in seen)


def test_a_crashing_agent_counts_as_a_failed_run():
    def scenario(probe):
        raise RuntimeError("agent crashed")

    result = run_repeated(scenario, runs=2)

    assert result.passes == 0 and len(result.failures) == 2


def test_runs_must_be_positive():
    with pytest.raises(ValueError):
        run_repeated(lambda probe: None, runs=0)
