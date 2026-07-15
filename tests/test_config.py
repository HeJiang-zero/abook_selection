from app.config import get_settings


def test_clickhouse_connection_options_are_read_from_environment(monkeypatch):
    monkeypatch.setenv("CLICKHOUSE_COMPRESS", "1")
    monkeypatch.setenv("CLICKHOUSE_USE_SERVER_TIME_ZONE_FOR_DATES", "true")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.clickhouse_compress is True
    assert settings.clickhouse_use_server_time_zone_for_dates is True

    get_settings.cache_clear()
