from __future__ import annotations

from typing import Any

from sqlalchemy import text

from backend.app.database.connection import create_db_engine


class DatabaseManager:
    def __init__(self) -> None:
        self.engine = create_db_engine()

    def fetch_one(self, sql: str) -> Any:
        with self.engine.connect() as connection:
            result = connection.execute(text(sql))
            return result.fetchone()

    def fetch_all(self, sql: str) -> list[tuple[Any, ...]]:
        with self.engine.connect() as connection:
            result = connection.execute(text(sql))
            return list(result.fetchall())
