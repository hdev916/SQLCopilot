from __future__ import annotations

import os
import time
from typing import Any

from sqlalchemy import text


def execute_read_only_query(
    engine: Any,
    sql: str,
    *,
    max_rows: int = 1000,
    statement_timeout_ms: int = 5000,
    lock_timeout_ms: int = 2000,
) -> dict[str, Any]:
    max_rows = int(os.getenv("SQLCOPILOT_MAX_ROWS", max_rows))
    statement_timeout_ms = int(
        os.getenv("SQLCOPILOT_STATEMENT_TIMEOUT_MS", statement_timeout_ms)
    )
    lock_timeout_ms = int(os.getenv("SQLCOPILOT_LOCK_TIMEOUT_MS", lock_timeout_ms))

    started = time.perf_counter()
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL TRANSACTION READ ONLY")
        connection.exec_driver_sql(
            f"SET LOCAL statement_timeout = '{statement_timeout_ms}ms'"
        )
        connection.exec_driver_sql(f"SET LOCAL lock_timeout = '{lock_timeout_ms}ms'")

        result = connection.execute(text(sql))
        rows = result.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        if truncated:
            rows = rows[:max_rows]

        columns = list(result.keys())

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "columns": columns,
        "rows": [dict(zip(columns, row)) for row in rows],
        "row_count": len(rows),
        "truncated": truncated,
        "execution_time_ms": elapsed_ms,
    }
