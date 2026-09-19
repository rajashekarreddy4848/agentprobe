pytest_plugins = ["pytester"]

from agentprobe.store import Store  # noqa: E402

TEST_FILE = """
import pytest

def lookup(order_id):
    return {"order_id": order_id}

def test_passes(probe):
    probe.wrap(lookup)(order_id="A1")

def test_fails(probe):
    probe.wrap(lookup)(order_id="A2")
    assert False

@pytest.mark.skip(reason="not now")
def test_skipped():
    pass

@pytest.mark.xfail(strict=True, reason="known bug")
def test_known_bug(probe):
    probe.wrap(lookup)(order_id="A3")
    assert False

def test_plain():
    pass
"""


def test_store_option_saves_every_test_with_trajectories(pytester):
    pytester.makepyfile(TEST_FILE)

    pytester.runpytest("--agentprobe-store=runs.db", "--agentprobe-label=abc123")

    store = Store(pytester.path / "runs.db")
    run = store.runs()[0]
    outcomes = {r["nodeid"].split("::")[-1]: r["outcome"] for r in store.run(run["id"])["results"]}
    assert run["label"] == "abc123"
    assert outcomes == {"test_passes": "PASSED", "test_fails": "FAILED", "test_skipped": "SKIPPED",
                        "test_known_bug": "XFAIL (bug caught)", "test_plain": "PASSED"}
    passes = next(r for r in store.run(run["id"])["results"] if r["nodeid"].endswith("test_passes"))
    assert passes["calls"][0]["tool"] == "lookup"
    store.close()


def test_each_run_is_saved_as_a_new_run(pytester):
    pytester.makepyfile(TEST_FILE)

    pytester.runpytest("--agentprobe-store=runs.db")
    pytester.runpytest("--agentprobe-store=runs.db")

    store = Store(pytester.path / "runs.db")
    assert len(store.runs()) == 2
    flaky_or_not = {t["nodeid"].split("::")[-1]: t["flaky"] for t in store.tests()}
    assert not any(flaky_or_not.values())  # same outcome both runs
    store.close()


def test_no_store_file_without_the_option(pytester):
    pytester.makepyfile(TEST_FILE)

    pytester.runpytest()

    assert not list(pytester.path.glob("*.db"))


def test_repeat_fixture_records_the_pass_rate_and_marks_the_test_flaky(pytester):
    pytester.makepyfile("""
        def test_mostly_ok(repeat):
            counter = {"n": 0}

            def scenario(probe):
                counter["n"] += 1
                assert counter["n"] != 2, "second run misbehaved"

            repeat(scenario, runs=5, min_pass_rate=0.8)
    """)

    result = pytester.runpytest("--agentprobe-store=runs.db")

    result.assert_outcomes(passed=1)
    store = Store(pytester.path / "runs.db")
    test = store.tests()[0]
    assert (test["repeat_runs"], test["repeat_passes"]) == (5, 4)
    assert test["flaky"] is True
    store.close()


def test_repeat_fixture_fails_the_test_below_the_required_rate(pytester):
    pytester.makepyfile("""
        def test_too_flaky(repeat):
            counter = {"n": 0}

            def scenario(probe):
                counter["n"] += 1
                assert counter["n"] % 2 == 0, "odd run misbehaved"

            repeat(scenario, runs=4, min_pass_rate=0.9)
    """)

    result = pytester.runpytest()

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*pass rate 50% (2/4) is below the required 90%*"])
