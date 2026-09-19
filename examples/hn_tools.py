"""Tools for a Hacker News agent. `get_top_stories` and `get_comments` call the REAL public
Hacker News API (no key needed); `send_email` is SIMULATED (it only returns a receipt).

Comments are written by strangers, so an agent reading them is reading untrusted text.
"""
import html
import json
import re
import urllib.request

BASE_URL = "https://hacker-news.firebaseio.com/v0"


def _get(path):
    request = urllib.request.Request(f"{BASE_URL}{path}", headers={"User-Agent": "agentprobe-demo/0.1"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read(200_000))


def _plain(text):
    return html.unescape(re.sub(r"<[^>]+>", " ", text or "")).strip()


def get_top_stories(limit=5):
    limit = max(1, min(int(limit), 10))  # keep traffic to the public API light
    stories = []
    for story_id in _get("/topstories.json")[:limit]:
        item = _get(f"/item/{story_id}.json") or {}
        stories.append({
            "id": item.get("id"), "title": item.get("title"), "score": item.get("score"),
            "by": item.get("by"), "url": item.get("url"), "comment_count": item.get("descendants", 0),
        })
    return stories


def get_comments(story_id, limit=3):
    limit = max(1, min(int(limit), 10))
    comments = []
    for comment_id in (_get(f"/item/{int(story_id)}.json") or {}).get("kids", [])[:limit]:
        item = _get(f"/item/{comment_id}.json") or {}
        if item.get("deleted") or item.get("dead"):
            continue
        comments.append({"by": item.get("by"), "text": _plain(item.get("text"))[:500]})
    return comments


def send_email(to, body):
    return {"status": "sent (simulated)", "to": to}


TOOLS = {f.__name__: f for f in (get_top_stories, get_comments, send_email)}
