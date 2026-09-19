import pytest

from agentprobe.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "runs.db")
    yield s
    s.close()


def record(store, results, label=None):
    run_id = store.start_run(label)
    for nodeid, outcome, *rest in results:
        store.add_result(run_id, nodeid, outcome, duration_ms=rest[0] if rest else 10.0)
    store.finish_run(run_id)
    return run_id


def test_run_summary_counts_and_pass_rate(store):
    record(store, [("t::a", "PASSED"), ("t::b", "XFAIL (bug caught)"), ("t::c", "FAILED"), ("t::d", "SKIPPED")])

    run = store.runs()[0]

    assert (run["passed"], run["caught"], run["failed"], run["skipped"], run["total"]) == (1, 1, 1, 1, 4)
    assert run["pass_rate"] == pytest.approx(2 / 3)  # skipped tests don't count either way


def test_runs_are_newest_first(store):
    first = record(store, [("t::a", "PASSED")], label="one")
    second = record(store, [("t::a", "PASSED")], label="two")

    assert [r["id"] for r in store.runs()] == [second, first]


def test_test_that_both_passes_and_fails_across_runs_is_flaky(store):
    record(store, [("t::steady", "PASSED"), ("t::wobbly", "PASSED")])
    record(store, [("t::steady", "PASSED"), ("t::wobbly", "FAILED")])

    by_id = {t["nodeid"]: t for t in store.tests()}

    assert by_id["t::wobbly"]["flaky"] is True
    assert by_id["t::wobbly"]["pass_rate"] == 0.5
    assert by_id["t::steady"]["flaky"] is False


def test_a_known_bug_that_is_always_caught_is_not_flaky(store):
    record(store, [("t::buggy", "XFAIL (bug caught)")])
    record(store, [("t::buggy", "XFAIL (bug caught)")])

    assert store.tests()[0]["flaky"] is False


def test_partial_repeat_pass_rate_marks_a_test_flaky_within_one_run(store):
    run_id = store.start_run()
    store.add_result(run_id, "t::llm", "PASSED", repeat={"runs": 10, "passes": 8})
    store.finish_run(run_id)

    test = store.tests()[0]

    assert test["flaky"] is True
    assert test["repeat_pass_rate"] == 0.8


def test_average_and_max_duration_ignore_skipped_runs(store):
    record(store, [("t::a", "PASSED", 100.0)])
    record(store, [("t::a", "PASSED", 300.0)])
    record(store, [("t::a", "SKIPPED", 0.0)])

    test = store.tests()[0]

    assert test["avg_duration_ms"] == 200.0
    assert test["max_duration_ms"] == 300.0


def test_run_detail_includes_trajectories(store):
    run_id = store.start_run()
    calls = [{"step": 1, "tool": "lookup", "args": {"id": "'A1'"}, "result": "'ok'", "error": None,
              "fault": None, "duration_ms": 1.0}]
    store.add_result(run_id, "t::a", "PASSED", calls=calls)
    store.finish_run(run_id)

    detail = store.run(run_id)

    assert detail["results"][0]["calls"][0]["tool"] == "lookup"
    assert store.run(999) is None


def test_tool_stats_count_calls_errors_and_faults(store):
    run_id = store.start_run()
    ok = {"step": 1, "tool": "lookup", "args": {}, "result": "'x'", "error": None, "fault": None, "duration_ms": 1}
    bad = {"step": 2, "tool": "lookup", "args": {}, "result": None, "error": "TimeoutError: x",
           "fault": "timeout", "duration_ms": 1}
    store.add_result(run_id, "t::a", "PASSED", calls=[ok, bad])
    store.finish_run(run_id)

    tool = store.tools()[0]

    assert (tool["calls"], tool["errors"], tool["faulted"], tool["error_rate"]) == (2, 1, 1, 0.5)


def test_test_history_is_ordered_by_run(store):
    record(store, [("t::a", "PASSED")])
    record(store, [("t::a", "FAILED")])

    assert [h["outcome"] for h in store.test_history("t::a")] == ["PASSED", "FAILED"]
