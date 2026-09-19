"""pytest plugin: `probe` and `repeat` fixtures, @pytest.mark.fault marker, trajectory in failure
reports, an HTML report of probed tests (`--agentprobe-report`), and a run history for the
dashboard (`--agentprobe-store`)."""
import pytest

from .recorder import Probe
from .repeat import run_repeated
from .report import save
from .store import Store, calls_to_json


def pytest_addoption(parser):
    group = parser.getgroup("agentprobe")
    group.addoption("--agentprobe-report", metavar="PATH", default=None,
                    help="write an HTML trajectory report for every test that used the `probe` fixture")
    group.addoption("--agentprobe-store", metavar="PATH", default=None,
                    help="save this run to a SQLite file for the dashboard (history, flaky tests, trends)")
    group.addoption("--agentprobe-label", metavar="TEXT", default=None,
                    help="label for the saved run, e.g. a commit SHA")


def pytest_configure(config):
    config.addinivalue_line("markers", "fault(tool, kind, **kwargs): inject a fault into a tool")
    config._agentprobe_results = []  # probed tests, for the HTML report
    config._agentprobe_all = []  # every test, for the run store


@pytest.fixture
def probe(request):
    p = Probe()
    for marker in request.node.iter_markers("fault"):
        tool, kind = marker.args
        p.inject(tool, kind, **marker.kwargs)
    request.node._agentprobe = p
    yield p


@pytest.fixture
def repeat(request):
    """repeat(scenario, runs=10, min_pass_rate=1.0, faults=()) -> RepeatResult. See agentprobe.repeat."""
    def _repeat(scenario, runs=10, min_pass_rate=1.0, faults=()):
        result = run_repeated(scenario, runs=runs, faults=faults)
        request.node._agentprobe_repeat = {"runs": result.runs, "passes": result.passes}
        request.node._agentprobe = result.failures[0][2] if result.failures else result.probes[-1]
        return result.require(min_pass_rate)
    return _repeat


def _outcome(report):
    if hasattr(report, "wasxfail"):
        return "XFAIL (bug caught)" if report.skipped else "XPASS"
    return report.outcome.upper()


def _final_outcome(report):
    """The one outcome to record per test, or None for phases that don't decide it."""
    if report.when == "call":
        return _outcome(report)
    if report.when == "setup" and report.skipped:
        return "SKIPPED"
    if report.when == "setup" and report.failed:
        return "FAILED"
    return None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    p = getattr(item, "_agentprobe", None)
    if p and report.when == "call" and p.calls:
        report.sections.append(("agentprobe trajectory", p.trajectory.timeline()))
        item.config._agentprobe_results.append((item.nodeid, p, _outcome(report)))
    final = _final_outcome(report)
    if final:
        item.config._agentprobe_all.append({
            "nodeid": item.nodeid,
            "outcome": final,
            "duration_ms": report.duration * 1000,
            "calls": calls_to_json(p.calls) if p else [],
            "repeat": getattr(item, "_agentprobe_repeat", None),
        })


def _write_html_report(config, terminal):
    path = config.getoption("agentprobe_report")
    results = config._agentprobe_results
    if not path or not results:
        return
    scenarios = {nodeid: (probe, outcome) for nodeid, probe, outcome in results}
    outcomes = [outcome for _, _, outcome in results]
    parts = [f"{outcomes.count('PASSED')} passed"]
    for label, text in (("XFAIL (bug caught)", "bugs caught"), ("FAILED", "failed"), ("XPASS", "unexpectedly passed")):
        if outcomes.count(label):
            parts.append(f"{outcomes.count(label)} {text}")
    save(scenarios, path, title=f"agentprobe test run: {', '.join(parts)}")
    if terminal:
        terminal.write_line(f"agentprobe report written to {path}")


def _save_run(config, terminal):
    path = config.getoption("agentprobe_store")
    if not path or not config._agentprobe_all:
        return
    store = Store(path)
    try:
        run_id = store.start_run(config.getoption("agentprobe_label"))
        for r in config._agentprobe_all:
            store.add_result(run_id, r["nodeid"], r["outcome"], r["duration_ms"], r["calls"], r["repeat"])
        store.finish_run(run_id)
    finally:
        store.close()
    if terminal:
        terminal.write_line(f"agentprobe run #{run_id} saved to {path}")


def pytest_sessionfinish(session):
    terminal = session.config.pluginmanager.get_plugin("terminalreporter")
    _write_html_report(session.config, terminal)
    _save_run(session.config, terminal)
