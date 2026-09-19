"""pytest plugin: `probe` fixture + @pytest.mark.fault marker + trajectory in failure reports
+ optional HTML report of every probed test (`--agentprobe-report PATH`)."""
import pytest

from .recorder import Probe
from .report import save


def pytest_addoption(parser):
    parser.getgroup("agentprobe").addoption(
        "--agentprobe-report",
        metavar="PATH",
        default=None,
        help="write an HTML trajectory report for every test that used the `probe` fixture",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "fault(tool, kind, **kwargs): inject a fault into a tool")
    config._agentprobe_results = []


@pytest.fixture
def probe(request):
    p = Probe()
    for marker in request.node.iter_markers("fault"):
        tool, kind = marker.args
        p.inject(tool, kind, **marker.kwargs)
    request.node._agentprobe = p
    yield p


def _outcome(report):
    if hasattr(report, "wasxfail"):
        return "XFAIL (bug caught)" if report.skipped else "XPASS"
    return report.outcome.upper()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    p = getattr(item, "_agentprobe", None)
    if p and report.when == "call" and p.calls:
        report.sections.append(("agentprobe trajectory", p.trajectory.timeline()))
        item.config._agentprobe_results.append((item.nodeid, p, _outcome(report)))


def pytest_sessionfinish(session):
    path = session.config.getoption("agentprobe_report")
    results = session.config._agentprobe_results
    if not path or not results:
        return
    scenarios = {nodeid: (probe, outcome) for nodeid, probe, outcome in results}
    outcomes = [outcome for _, _, outcome in results]
    parts = [f"{outcomes.count('PASSED')} passed"]
    for label, text in (("XFAIL (bug caught)", "bugs caught"), ("FAILED", "failed"), ("XPASS", "unexpectedly passed")):
        if outcomes.count(label):
            parts.append(f"{outcomes.count(label)} {text}")
    save(scenarios, path, title=f"agentprobe test run: {', '.join(parts)}")
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter:
        reporter.write_line(f"agentprobe report written to {path}")
