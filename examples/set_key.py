"""Safely save an API key from your clipboard into .env.

    python -m examples.set_key                    # saves OPENAI_API_KEY
    python -m examples.set_key ANTHROPIC_API_KEY  # any variable name

It keeps only the first word of what you copied (so stray text can't sneak in), replaces any old
line for that name, never prints the key (only its prefix and length), and if .env points at
OpenRouter it checks with OpenRouter that the key is recognized.
"""
import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


def first_token(text):
    parts = text.split()
    return parts[0] if parts else ""


def upsert(env_text, name, value):
    """Set NAME=value: replace the first NAME= line, drop duplicates, or append if missing."""
    out, done = [], False
    for line in env_text.split("\n"):
        if line.startswith(name + "="):
            if not done:
                out.append(f"{name}={value}")
                done = True
            continue
        out.append(line)
    if not done:
        if out and out[-1] == "":
            out.pop()
        out.append(f"{name}={value}")
    text = "\n".join(out)
    return text if text.endswith("\n") else text + "\n"


def env_value(env_text, name):
    for line in env_text.split("\n"):
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip()
    return None


def check_openrouter(key):
    """(recognized, message) from OpenRouter's key endpoint. Never includes the key."""
    request = urllib.request.Request("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status == 200, "OpenRouter recognizes this key."
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get("error", {}).get("message", "")
        except ValueError:
            detail = ""
        return False, f"OpenRouter rejected the key ({e.code}: {detail or 'no detail'})."
    except OSError as e:
        return False, f"Couldn't reach OpenRouter to check the key ({e})."


def main(argv=None):
    parser = argparse.ArgumentParser(description="Save an API key from your clipboard into .env")
    parser.add_argument("name", nargs="?", default="OPENAI_API_KEY")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--stdin", action="store_true", help="read the key from stdin instead of the clipboard (non-macOS)")
    args = parser.parse_args(argv)

    raw = sys.stdin.read() if args.stdin else subprocess.check_output(["pbpaste"], text=True)
    key = first_token(raw)
    if not key:
        raise SystemExit("Your clipboard is empty. Copy the key first, then run this again.")

    path = Path(args.env)
    env_text = path.read_text() if path.exists() else ""
    path.write_text(upsert(env_text, args.name, key))
    print(f"Saved {args.name} to {path} (starts with {key[:9]!r}, {len(key)} characters).")

    if "openrouter.ai" in (env_value(path.read_text(), "OPENAI_BASE_URL") or "") and args.name == "OPENAI_API_KEY":
        recognized, message = check_openrouter(key)
        print(message)
        if not recognized:
            print("Create a fresh key at https://openrouter.ai/keys, copy it, and run this command again.")
            raise SystemExit(1)


if __name__ == "__main__":
    main()
