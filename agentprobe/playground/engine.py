"""Playground engine: run a DESCRIBED agent (system prompt + simulated tools) on a real model, inject
failures into the tools, and check the recorded trajectory.

Safe by design: nothing the user writes is executed. A tool is just a name, a description, parameters and
a fixed result (with $param placeholders filled from the model's arguments). Models are reached over plain
HTTP (Ollama, or any OpenAI-compatible API such as OpenAI and OpenRouter), so this needs no extra packages.
"""
import json
import re
import string
import urllib.error
import urllib.request

from ..assertions import TrajectoryAssertionError
from ..faults import FAULTS
from ..recorder import Probe
from ..store import calls_to_json

MAX_TOOLS = 12
MAX_RUNS = 10
MAX_TURNS = 8
TIMEOUT_SECONDS = 120
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,39}$")
_TYPES = {"string", "number", "integer", "boolean"}


class PlaygroundError(Exception):
    """A problem the user can fix (bad config, model unreachable). The message is safe to show."""


def scrub(text, secret):
    return text.replace(secret, "***") if secret else text


# ---------- tools ----------

def _make_tool(name, template):
    def tool(**kwargs):
        text = string.Template(template).safe_substitute({k: str(v) for k, v in kwargs.items()})
        try:
            return json.loads(text)
        except ValueError:
            return text  # not JSON: hand the model the plain text

    tool.__name__ = name
    return tool


def build_tools(specs):
    """[{name, description, params: [{name, type, description}], result}] -> (tools dict, OpenAI-style schemas)."""
    if not isinstance(specs, list) or not specs:
        raise PlaygroundError("Add at least one tool.")
    if len(specs) > MAX_TOOLS:
        raise PlaygroundError(f"At most {MAX_TOOLS} tools.")
    tools, schemas = {}, []
    for spec in specs:
        name = str(spec.get("name", "")).strip()
        if not _NAME.match(name):
            raise PlaygroundError(f"Tool name {name!r} must be letters, digits and underscores, starting with a letter.")
        if name in tools:
            raise PlaygroundError(f"Two tools are named {name!r}.")
        properties = {}
        for param in spec.get("params", []):
            pname = str(param.get("name", "")).strip()
            if not _NAME.match(pname):
                raise PlaygroundError(f"Parameter name {pname!r} (tool {name!r}) must be letters, digits and underscores.")
            ptype = param.get("type", "string")
            properties[pname] = {"type": ptype if ptype in _TYPES else "string"}
            if param.get("description"):
                properties[pname]["description"] = str(param["description"])[:200]
        tools[name] = _make_tool(name, str(spec.get("result", "")))
        schemas.append({"type": "function", "function": {
            "name": name, "description": str(spec.get("description", ""))[:500],
            "parameters": {"type": "object", "properties": properties, "required": list(properties)}}})
    return tools, schemas


# ---------- faults and checks ----------

def apply_faults(probe, faults, tool_names):
    for fault in faults or []:
        tool, kind = fault.get("tool"), fault.get("kind")
        if kind in (None, "", "none"):
            continue
        if tool not in tool_names:
            raise PlaygroundError(f"Failure targets unknown tool {tool!r}.")
        if kind not in FAULTS:
            raise PlaygroundError(f"Unknown failure {kind!r}. Options: {', '.join(FAULTS)}.")
        options = {}
        if kind == "prompt_injection":
            if fault.get("payload"):
                options["payload"] = str(fault["payload"])[:1000]
            if fault.get("field"):
                options["field"] = str(fault["field"])[:60]
        probe.inject(tool, kind, **options)


def build_checks(spec, tool_names):
    """No-code check spec -> [(label, fn(trajectory))]."""
    spec = spec or {}

    def known(name):
        if name not in tool_names:
            raise PlaygroundError(f"A check mentions unknown tool {name!r}.")
        return name

    checks = []
    for t in spec.get("must_call", []):
        checks.append((f"Calls {known(t)}", lambda tr, t=t: tr.called(t)))
    for t in spec.get("never_called", []):
        checks.append((f"Never calls {known(t)}", lambda tr, t=t: tr.never_called(t)))
    for rule in spec.get("order", []):
        a, b, kind = known(rule.get("first")), known(rule.get("then")), rule.get("kind", "before")
        if kind == "after_success":
            checks.append((f"Calls {b} only after {a} succeeded", lambda tr, a=a, b=b: tr.called_after_success(a, b)))
        else:
            checks.append((f"Calls {a} before {b}", lambda tr, a=a, b=b: tr.called_before(a, b)))
    if spec.get("max_steps"):
        n = int(spec["max_steps"])
        checks.append((f"Takes at most {n} tool calls", lambda tr, n=n: tr.max_steps(n)))
    return checks


# ---------- models over HTTP ----------

def _post_json(url, payload, headers, secret):
    if not url.startswith(("http://", "https://")):
        raise PlaygroundError("The model address must start with http:// or https://")
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "agentprobe-playground", **headers})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        body = scrub(e.read(600).decode("utf-8", "replace"), secret)
        raise PlaygroundError(f"The model server answered {e.code}: {body}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise PlaygroundError(f"Couldn't reach the model server: {scrub(str(getattr(e, 'reason', e)), secret)}") from None
    except ValueError:
        raise PlaygroundError("The model server sent something that isn't JSON.") from None


def _tool_result_text(tools, name, args):
    if name not in tools:
        return f"ERROR: unknown tool {name!r}"
    try:
        result = tools[name](**args)
        return result if isinstance(result, str) else json.dumps(result)
    except Exception as e:  # a faulted tool: the model sees the failure as text
        return f"ERROR: {type(e).__name__}: {e}"


def run_agent(provider, system, message, tools, schemas):
    kind = provider.get("kind", "ollama")
    model, key = provider.get("model", ""), provider.get("api_key", "") or ""
    if not model:
        raise PlaygroundError("Choose a model.")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": message}]

    for _ in range(MAX_TURNS):
        if kind == "ollama":
            base = (provider.get("base_url") or "http://localhost:11434").rstrip("/")
            data = _post_json(f"{base}/api/chat", {
                "model": model, "messages": messages, "tools": schemas, "stream": False,
                "options": {"temperature": float(provider.get("temperature", 0))}}, {}, key)
            msg = data.get("message") or {}
            calls = [(None, c["function"]["name"], c["function"].get("arguments") or {}) for c in msg.get("tool_calls") or []]
            assistant = msg
        else:
            base = (provider.get("base_url") or "https://api.openai.com/v1").rstrip("/")
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            data = _post_json(f"{base}/chat/completions", {"model": model, "messages": messages, "tools": schemas}, headers, key)
            try:
                msg = data["choices"][0]["message"]
            except (KeyError, IndexError, TypeError):
                raise PlaygroundError(f"Unexpected reply from the model server: {scrub(json.dumps(data)[:300], key)}") from None
            calls = []
            for c in msg.get("tool_calls") or []:
                raw = c["function"].get("arguments") or "{}"
                try:
                    args = json.loads(raw) if isinstance(raw, str) else raw
                except ValueError:
                    args = None
                calls.append((c["id"], c["function"]["name"], args))
            assistant = {"role": "assistant", "content": msg.get("content"), "tool_calls": msg.get("tool_calls")} if calls else msg

        if not calls:
            return msg.get("content") or ""
        messages.append(assistant)
        for call_id, name, args in calls:
            text = "ERROR: arguments were not valid JSON" if args is None else _tool_result_text(tools, name, args)
            messages.append({"role": "tool", "content": text, **({"tool_call_id": call_id} if call_id else {})})
    return "Stopped: hit max turns."


# ---------- one full request ----------

def run_playground(request):
    """Run the described agent `runs` times. Returns {runs: [...], passed, total, pass_rate}."""
    tools, schemas = build_tools(request.get("tools"))
    system = str(request.get("system", ""))[:8000]
    message = str(request.get("message", "")).strip()[:4000]
    if not message:
        raise PlaygroundError("Write the message the customer sends to the agent.")
    provider = request.get("provider") or {}
    checks = build_checks(request.get("checks"), set(tools))
    faults = request.get("faults") or []
    runs = max(1, min(int(request.get("runs") or 1), MAX_RUNS))
    secret = provider.get("api_key") or ""

    results = []
    for _ in range(runs):
        probe = Probe()
        apply_faults(probe, faults, set(tools))
        try:
            reply = run_agent(provider, system, message, probe.wrap(tools), schemas)
        except PlaygroundError as e:
            raise PlaygroundError(scrub(str(e), secret)) from None
        verdicts = []
        for name, check in checks:
            try:
                check(probe.trajectory)
                verdicts.append({"name": name, "passed": True})
            except TrajectoryAssertionError as e:
                verdicts.append({"name": name, "passed": False, "detail": str(e).split("\n")[0]})
        results.append({"reply": reply, "calls": calls_to_json(probe.calls), "checks": verdicts,
                        "passed": all(v["passed"] for v in verdicts)})
    passed = sum(1 for r in results if r["passed"])
    return {"runs": results, "passed": passed, "total": len(results), "pass_rate": passed / len(results)}
