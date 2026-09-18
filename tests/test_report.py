from agentprobe import Probe, render_report

from examples.refund_agent import TOOLS, safe_refund_agent


def test_render_includes_scenario_labels_and_calls():
    probe = Probe()
    safe_refund_agent("Hi, please refund order A123", probe.wrap(TOOLS))

    html = render_report({"Happy path": probe})

    assert "Happy path" in html
    assert "lookup_order" in html
    assert "issue_refund" in html


def test_render_handles_empty_trajectory():
    html = render_report({"Nothing happened": Probe()})
    assert "(no tool calls)" in html


def test_render_accepts_scenario_note():
    probe = Probe()
    safe_refund_agent("Hi, please refund order A123", probe.wrap(TOOLS))

    html = render_report({"Happy path": (probe, "Refunded blindly? False")})

    assert "Refunded blindly? False" in html


def test_escapes_untrusted_content():
    probe = Probe()
    probe.wrap(TOOLS)["escalate_to_human"](reason="<script>alert(1)</script>")

    html = render_report({"XSS check": probe})

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
