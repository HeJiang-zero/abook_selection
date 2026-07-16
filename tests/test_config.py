from app.config import get_settings, load_env_file


def test_load_env_file_populates_missing_environment_values(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("CLICKHOUSE_HOST=local-host\nCLICKHOUSE_PORT=9000\n# ignored\n")
    monkeypatch.delenv("CLICKHOUSE_HOST", raising=False)
    monkeypatch.delenv("CLICKHOUSE_PORT", raising=False)

    load_env_file(env_file)

    assert __import__("os").environ["CLICKHOUSE_HOST"] == "local-host"
    assert __import__("os").environ["CLICKHOUSE_PORT"] == "9000"


def test_clickhouse_connection_options_are_read_from_environment(monkeypatch):
    monkeypatch.setenv("CLICKHOUSE_COMPRESS", "1")
    monkeypatch.setenv("CLICKHOUSE_USE_SERVER_TIME_ZONE_FOR_DATES", "true")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.clickhouse_compress is True
    assert settings.clickhouse_use_server_time_zone_for_dates is True

    get_settings.cache_clear()
