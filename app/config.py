from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    clickhouse_host: str
    clickhouse_port: int
    clickhouse_database: str
    clickhouse_user: str
    clickhouse_password: str
    clickhouse_secure: bool

    @property
    def configured(self) -> bool:
        return bool(self.clickhouse_host and self.clickhouse_user and self.clickhouse_password)


@lru_cache
def get_settings() -> Settings:
    return Settings(
        clickhouse_host=os.getenv(
            "CLICKHOUSE_HOST",
            "data-collect-alb-110459182.ap-southeast-2.elb.amazonaws.com",
        ),
        clickhouse_port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        clickhouse_database=os.getenv("CLICKHOUSE_DATABASE", "risk"),
        clickhouse_user=os.getenv("CLICKHOUSE_USER", "default"),
        clickhouse_password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        clickhouse_secure=os.getenv("CLICKHOUSE_SECURE", "0").lower() in {"1", "true", "yes"},
    )
