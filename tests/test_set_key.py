from examples.set_key import env_value, first_token, main, upsert


def test_first_token_drops_stray_text_after_the_key():
    assert first_token("sk-or-v1-abc >> .env\n") == "sk-or-v1-abc"
    assert first_token("   \n") == ""


def test_upsert_replaces_the_existing_line_and_keeps_the_rest():
    result = upsert("A=1\nOPENAI_API_KEY=old\nB=2\n", "OPENAI_API_KEY", "new")

    assert result == "A=1\nOPENAI_API_KEY=new\nB=2\n"


def test_upsert_drops_duplicate_lines_for_the_same_name():
    result = upsert("KEY=one\nX=1\nKEY=two\n", "KEY", "three")

    assert result == "KEY=three\nX=1\n"


def test_upsert_appends_when_missing_and_handles_a_missing_final_newline():
    assert upsert("A=1", "B", "2") == "A=1\nB=2\n"
    assert upsert("", "B", "2") == "B=2\n"


def test_upsert_does_not_touch_a_variable_with_a_similar_name():
    assert upsert("OPENAI_API_KEY_OLD=x\n", "OPENAI_API_KEY", "y") == "OPENAI_API_KEY_OLD=x\nOPENAI_API_KEY=y\n"


def test_env_value():
    assert env_value("A=1\nB=two\n", "B") == "two"
    assert env_value("A=1\n", "B") is None


def test_main_saves_only_the_key_and_never_prints_it(tmp_path, monkeypatch, capsys):
    env = tmp_path / ".env"
    env.write_text("OPENAI_BASE_URL=https://example.com/v1\nOPENAI_API_KEY=stale\n")
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("sk-secret-value-123 >> .env"))

    main(["OPENAI_API_KEY", "--env", str(env), "--stdin"])

    assert env.read_text() == "OPENAI_BASE_URL=https://example.com/v1\nOPENAI_API_KEY=sk-secret-value-123\n"
    assert "sk-secret-value-123" not in capsys.readouterr().out
