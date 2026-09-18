"""HTML trajectory report: a shareable, visual rendering of one or more probe runs."""
import html
from datetime import datetime, timezone

from .assertions import Trajectory

_CSS = """
:root {
  --bg: #ffffff; --fg: #1a1a1a; --muted: #6b7280; --border: #e5e7eb;
  --card: #f9fafb; --ok: #059669; --err: #dc2626; --fault: #d97706;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1115; --fg: #e5e7eb; --muted: #9ca3af; --border: #2a2e37;
    --card: #171a21; --ok: #34d399; --err: #f87171; --fault: #fbbf24;
  }
}
* { box-sizing: border-box; }
body {
  background: var(--bg); color: var(--fg); margin: 0; padding: 2rem 1rem;
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
main { max-width: 780px; margin: 0 auto; }
h1 { font-size: 1.4rem; margin: 0 0 0.25rem; }
.meta { color: var(--muted); font-size: 0.85rem; margin-bottom: 2rem; }
.scenario { border: 1px solid var(--border); border-radius: 10px; margin-bottom: 1.5rem; overflow: hidden; }
.scenario h2 {
  font-size: 1rem; margin: 0; padding: 0.85rem 1.1rem; background: var(--card);
  border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;
}
.note { font-size: 0.85rem; color: var(--muted); font-weight: normal; }
ol.steps { list-style: none; margin: 0; padding: 0.5rem 1.1rem 1rem; }
ol.steps li { padding: 0.6rem 0; border-bottom: 1px dashed var(--border); font-family: var(--mono); font-size: 0.85rem; }
ol.steps li:last-child { border-bottom: none; }
.step-head { display: flex; align-items: baseline; gap: 0.5rem; flex-wrap: wrap; }
.step-num { color: var(--muted); }
.tool { font-weight: 600; }
.badge {
  font-family: -apple-system, sans-serif; font-size: 0.7rem; font-weight: 600;
  padding: 0.1rem 0.5rem; border-radius: 999px; text-transform: uppercase; letter-spacing: 0.02em;
}
.badge.fault { background: color-mix(in srgb, var(--fault) 18%, transparent); color: var(--fault); }
.badge.error { background: color-mix(in srgb, var(--err) 18%, transparent); color: var(--err); }
.badge.ok { background: color-mix(in srgb, var(--ok) 18%, transparent); color: var(--ok); }
.result { color: var(--muted); margin-top: 0.2rem; padding-left: 1.2rem; word-break: break-word; }
.result.error { color: var(--err); }
.empty { color: var(--muted); font-style: italic; padding: 1rem 1.1rem; }
"""


def _badge(text, kind):
    return f'<span class="badge {kind}">{html.escape(text)}</span>'


def _format_call(c):
    args = ", ".join(
        [repr(a) for a in c.args] + [f"{k}={v!r}" for k, v in c.kwargs.items()]
    )
    badges = []
    if c.fault:
        badges.append(_badge(f"fault: {c.fault}", "fault"))
    badges.append(_badge("error", "error") if c.error else _badge("ok", "ok"))

    outcome = html.escape(f"ERROR {c.error}" if c.error else f"-> {c.result!r}")
    outcome_class = "result error" if c.error else "result"

    return f"""<li>
  <div class="step-head">
    <span class="step-num">{c.step}.</span>
    <span class="tool">{html.escape(c.tool)}({html.escape(args)})</span>
    {' '.join(badges)}
  </div>
  <div class="{outcome_class}">{outcome}</div>
</li>"""


def _as_trajectory(value):
    if isinstance(value, Trajectory):
        return value
    if hasattr(value, "trajectory"):  # a Probe
        return value.trajectory
    raise TypeError(f"Expected a Trajectory or Probe, got {type(value).__name__}")


def _render_scenario(label, value, note=None):
    if isinstance(value, tuple):
        value, note = value
    traj = _as_trajectory(value)
    body = (
        "\n".join(_format_call(c) for c in traj.calls)
        if traj.calls
        else '<div class="empty">(no tool calls)</div>'
    )
    steps_html = f'<ol class="steps">{body}</ol>' if traj.calls else body
    note_html = f'<span class="note">{html.escape(note)}</span>' if note else ""
    return f"""<section class="scenario">
  <h2><span>{html.escape(label)}</span>{note_html}</h2>
  {steps_html}
</section>"""


def render(scenarios, title="agentprobe trajectory report"):
    """Render one or more scenarios to a self-contained HTML string.

    `scenarios` maps a label to a Trajectory, a Probe, or (Trajectory|Probe, note) —
    e.g. {"Normal run": probe1, "Chaos: timeout": (probe2, "Did it refund blindly? False")}.
    """
    sections = "\n".join(_render_scenario(label, value) for label, value in scenarios.items())
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<main>
  <h1>{html.escape(title)}</h1>
  <div class="meta">generated {timestamp} · agentprobe</div>
  {sections}
</main>
</body>
</html>"""


def save(scenarios, path, title="agentprobe trajectory report"):
    """Render scenarios and write them to `path`. Returns `path`."""
    with open(path, "w") as f:
        f.write(render(scenarios, title=title))
    return path
