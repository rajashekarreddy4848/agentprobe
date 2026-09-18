"""pytest plugin: `probe` fixture + @pytest.mark.fault marker + trajectory in failure reports."""
import pytest

from .recorder import Probe


def pytest_configure(config):
    config.addinivalue_line("markers", "fault(tool, kind, **kwargs): inject a fault into a tool")


@pytest.fixture
def probe(request):
    p = Probe()
    for marker in request.node.iter_markers("fault"):
        tool, kind = marker.args
        p.inject(tool, kind, **marker.kwargs)
    request.node._agentprobe = p
    yield p


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    p = getattr(item, "_agentprobe", None)
    if p and report.when == "call" and p.calls:
        report.sections.append(("agentprobe trajectory", p.trajectory.timeline()))
