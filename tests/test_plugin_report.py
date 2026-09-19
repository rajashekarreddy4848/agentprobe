pytest_plugins = ["pytester"]


def test_report_option_writes_html_for_probed_tests(pytester):
    pytester.makepyfile(
        """
        def test_uses_probe(probe):
            def lookup():
                return "ok"
            probe.wrap(lookup)()
        """
    )

    result = pytester.runpytest("--agentprobe-report=out.html")

    result.assert_outcomes(passed=1)
    html = (pytester.path / "out.html").read_text()
    assert "test_uses_probe" in html
    assert "lookup" in html
    assert "PASSED" in html


def test_no_report_without_option(pytester):
    pytester.makepyfile(
        """
        def test_uses_probe(probe):
            def lookup():
                return "ok"
            probe.wrap(lookup)()
        """
    )

    pytester.runpytest()

    assert not (pytester.path / "out.html").exists()
