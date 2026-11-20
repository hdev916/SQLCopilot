from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

load_dotenv(Path(__file__).resolve().parents[3] / ".env")


class DatabaseConfig:
    def __init__(self) -> None:
        self.host = os.getenv("DB_HOST", "localhost")
        self.port = os.getenv("DB_PORT", "5432")
        self.database = os.getenv("DB_NAME", "postgres")
        self.user = os.getenv("DB_USER", "postgres")
        self.password = os.getenv("DB_PASSWORD", "postgres")
        self.sslmode = os.getenv("DB_SSLMODE", "prefer")

    @property
    def sqlalchemy_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/"
            f"{self.database}?sslmode={self.sslmode}"
        )


def create_db_engine() -> Engine:
    config = DatabaseConfig()
    return create_engine(config.sqlalchemy_url, pool_pre_ping=True, future=True)


def test_connection() -> dict[str, Any]:
    engine = create_db_engine()
    with engine.connect() as connection:
        result = connection.execute(text("SELECT version() AS version;"))
        version = result.fetchone()[0]
    return {
        "status": "ok",
        "database": "postgresql",
        "version": version,
    }
