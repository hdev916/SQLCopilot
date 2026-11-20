from __future__ import annotations

from typing import Any


def find_foreign_keys(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    relationships: dict[str, list[str]] = {}
    for row in rows:
        if row.get("constraint_type") == "FOREIGN KEY":
            table_name = row.get("table_name")
            if table_name:
                relationships.setdefault(table_name, []).append(row.get("column_name", ""))
    return relationships
