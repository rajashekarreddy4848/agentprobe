"""One tool-calling loop for any provider, so a new domain doesn't need a new copy of it.

    schemas = tool_schemas(SPEC)
    run_ollama(message, tools, schemas, SYSTEM)     # free, local
    run_openai(message, tools, schemas, SYSTEM)     # OpenAI, or OpenRouter free models via OPENAI_BASE_URL

`tools` is the (probe-wrapped) dict of callables. Failures reach the model as "ERROR: ..." text.
"""
import json
import os
import warnings


def tool_schemas(spec):
    """{name: (description, {param: (json_type, description)}, [required])} -> OpenAI-style tool list."""
    schemas = []
    for name, (description, params, required) in spec.items():
        schemas.append({"type": "function", "function": {
            "name": name, "description": description,
            "parameters": {"type": "object",
                           "properties": {p: {"type": t, "description": d} for p, (t, d) in params.items()},
                           "required": list(required)}}})
    return schemas


def _result_text(tools, name, args):
    try:
        result = tools[name](**args)
        return result if isinstance(result, str) else json.dumps(result)
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def run_ollama(message, tools, schemas, system, model="qwen2.5:3b", temperature=0, max_turns=8):
    import ollama

    messages = [{"role": "system", "content": system}, {"role": "user", "content": message}]
    for _ in range(max_turns):
        response = ollama.chat(model=model, messages=messages, tools=schemas, options={"temperature": temperature})
        msg = response["message"]
        if not msg.get("tool_calls"):
            return msg.get("content", "")
        messages.append(msg)
        for call in msg["tool_calls"]:
            name, args = call["function"]["name"], dict(call["function"]["arguments"])
            messages.append({"role": "tool", "content": _result_text(tools, name, args)})
    return "Stopped: hit max turns."


def run_openai(message, tools, schemas, system, model=None, max_turns=8):
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv()
    model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if "openrouter.ai" in os.getenv("OPENAI_BASE_URL", "") and not (model.endswith(":free") or model == "openrouter/free"):
        warnings.warn(f"{model!r} doesn't look like a free OpenRouter model; calls to it may cost money.", stacklevel=2)
    client = OpenAI()

    messages = [{"role": "system", "content": system}, {"role": "user", "content": message}]
    for _ in range(max_turns):
        msg = client.chat.completions.create(model=model, messages=messages, tools=schemas).choices[0].message
        if not msg.tool_calls:
            return msg.content or ""
        messages.append({
            "role": "assistant", "content": msg.content,
            "tool_calls": [{"id": c.id, "type": "function",
                            "function": {"name": c.function.name, "arguments": c.function.arguments}} for c in msg.tool_calls],
        })
        for call in msg.tool_calls:
            try:
                args = json.loads(call.function.arguments)
            except ValueError:
                messages.append({"role": "tool", "tool_call_id": call.id, "content": "ERROR: arguments were not valid JSON"})
                continue
            messages.append({"role": "tool", "tool_call_id": call.id, "content": _result_text(tools, call.function.name, args)})
    return "Stopped: hit max turns."
