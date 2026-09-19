"""Run store: every pytest run, saved to SQLite, so results can be compared across runs
(history, flaky tests, slow tests, trends). Local-first: one file, no server, no account.
"""
import json
import sqlite3
from datetime import datetime, timezone

OK = ("PASSED", "XFAIL (bug caught)")  # healthy: passed, or a known-buggy agent that was caught
BAD = ("FAILED", "XPASS")
SKIPPED = "SKIPPED"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    label TEXT
);
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    nodeid TEXT NOT NULL,
    outcome TEXT NOT NULL,
    duration_ms REAL NOT NULL DEFAULT 0,
    calls TEXT NOT NULL DEFAULT '[]',
    repeat_runs INTEGER,
    repeat_passes INTEGER
);
CREATE INDEX IF NOT EXISTS results_run ON results(run_id);
CREATE INDEX IF NOT EXISTS results_node ON results(nodeid);
"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def calls_to_json(calls):
    """ToolCall objects -> JSON-safe dicts (values are repr'd, so any Python object is fine)."""
    return [
        {
            "step": c.step,
            "tool": c.tool,
            "args": {**{f"arg{i}": repr(a) for i, a in enumerate(c.args)},
                     **{k: repr(v) for k, v in c.kwargs.items()}},
            "result": None if c.error else repr(c.result),
            "error": c.error,
            "fault": c.fault,
            "duration_ms": round(c.duration_ms, 2),
        }
        for c in calls
    ]


def _rate(ok, bad):
    return ok / (ok + bad) if ok + bad else None


class Store:
    def __init__(self, path):
        self.path = str(path)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)

    def close(self):
        self.db.close()

    # ---- writing ----

    def start_run(self, label=None):
        cur = self.db.execute("INSERT INTO runs (started_at, label) VALUES (?, ?)", (_now(), label))
        self.db.commit()
        return cur.lastrowid

    def add_result(self, run_id, nodeid, outcome, duration_ms=0.0, calls=(), repeat=None):
        self.db.execute(
            "INSERT INTO results (run_id, nodeid, outcome, duration_ms, calls, repeat_runs, repeat_passes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, nodeid, outcome, duration_ms, json.dumps(list(calls)),
             repeat["runs"] if repeat else None, repeat["passes"] if repeat else None),
        )

    def finish_run(self, run_id):
        self.db.execute("UPDATE runs SET finished_at = ? WHERE id = ?", (_now(), run_id))
        self.db.commit()

    # ---- reading ----

    def runs(self):
        """All runs, newest first, each with outcome counts and a pass rate."""
        counts = {}
        for row in self.db.execute("SELECT run_id, outcome, COUNT(*) n FROM results GROUP BY run_id, outcome"):
            counts.setdefault(row["run_id"], {})[row["outcome"]] = row["n"]
        out = []
        for row in self.db.execute("SELECT * FROM runs ORDER BY id DESC"):
            c = counts.get(row["id"], {})
            ok = sum(c.get(o, 0) for o in OK)
            bad = sum(c.get(o, 0) for o in BAD)
            out.append({
                "id": row["id"], "label": row["label"], "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "passed": c.get("PASSED", 0), "caught": c.get("XFAIL (bug caught)", 0),
                "failed": bad, "skipped": c.get(SKIPPED, 0),
                "total": sum(c.values()), "pass_rate": _rate(ok, bad),
            })
        return out

    def run(self, run_id):
        summary = next((r for r in self.runs() if r["id"] == run_id), None)
        if summary is None:
            return None
        rows = self.db.execute("SELECT * FROM results WHERE run_id = ? ORDER BY id", (run_id,))
        summary["results"] = [
            {"nodeid": r["nodeid"], "outcome": r["outcome"], "duration_ms": r["duration_ms"],
             "calls": json.loads(r["calls"]), "repeat_runs": r["repeat_runs"], "repeat_passes": r["repeat_passes"]}
            for r in rows
        ]
        return summary

    def tests(self):
        """Per-test stats across all runs: pass rate, flaky flag, duration, last outcome."""
        stats = {}
        rows = self.db.execute(
            "SELECT r.nodeid, r.outcome, r.duration_ms, r.run_id, r.repeat_runs, r.repeat_passes "
            "FROM results r ORDER BY r.run_id, r.id"
        )
        for r in rows:
            s = stats.setdefault(r["nodeid"], {
                "nodeid": r["nodeid"], "ok": 0, "bad": 0, "skipped": 0, "durations": [],
                "last_outcome": None, "last_run_id": None, "repeat_runs": 0, "repeat_passes": 0,
                "partial_repeat": False,
            })
            if r["outcome"] in OK:
                s["ok"] += 1
            elif r["outcome"] in BAD:
                s["bad"] += 1
            else:
                s["skipped"] += 1
            if r["outcome"] != SKIPPED:
                s["durations"].append(r["duration_ms"])
            if r["repeat_runs"]:
                s["repeat_runs"] += r["repeat_runs"]
                s["repeat_passes"] += r["repeat_passes"]
                s["partial_repeat"] = s["partial_repeat"] or 0 < r["repeat_passes"] < r["repeat_runs"]
            s["last_outcome"], s["last_run_id"] = r["outcome"], r["run_id"]

        out = []
        for s in stats.values():
            durations = s.pop("durations")
            out.append({
                **s,
                "runs": s["ok"] + s["bad"],
                "pass_rate": _rate(s["ok"], s["bad"]),
                "repeat_pass_rate": s["repeat_passes"] / s["repeat_runs"] if s["repeat_runs"] else None,
                "flaky": (s["ok"] > 0 and s["bad"] > 0) or s["partial_repeat"],
                "avg_duration_ms": sum(durations) / len(durations) if durations else 0.0,
                "max_duration_ms": max(durations) if durations else 0.0,
            })
        return sorted(out, key=lambda t: t["nodeid"])

    def test_history(self, nodeid):
        rows = self.db.execute(
            "SELECT r.run_id, runs.started_at, r.outcome, r.duration_ms, r.repeat_runs, r.repeat_passes "
            "FROM results r JOIN runs ON runs.id = r.run_id WHERE r.nodeid = ? ORDER BY r.run_id",
            (nodeid,),
        )
        return [dict(r) for r in rows]

    def tools(self):
        """Tool-call stats across all runs: how often each tool was called, failed, or was faulted."""
        stats = {}
        for row in self.db.execute("SELECT calls FROM results WHERE calls != '[]'"):
            for call in json.loads(row["calls"]):
                s = stats.setdefault(call["tool"], {"tool": call["tool"], "calls": 0, "errors": 0, "faulted": 0})
                s["calls"] += 1
                s["errors"] += 1 if call["error"] else 0
                s["faulted"] += 1 if call["fault"] else 0
        return sorted(
            ({**s, "error_rate": s["errors"] / s["calls"]} for s in stats.values()),
            key=lambda t: -t["calls"],
        )
