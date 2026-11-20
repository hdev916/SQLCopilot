from __future__ import annotations

from typing import Any

from backend.app.schema_engine.relevance import select_relevant_tables


try:
    from backend.app.schema_engine.ai_selector import (
        SchemaSelectionError,
        select_relevant_schema,
    )
except ModuleNotFoundError:  # pragma: no cover - allows running from backend folder
    from app.schema_engine.ai_selector import SchemaSelectionError, select_relevant_schema

async def build_relevant_schema(
    question: str, schema: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    try:
        return await select_relevant_schema(question, schema)
    except SchemaSelectionError:
        tables = select_relevant_tables(question, schema)
        return {
            "tables": tables,
            "schema": {table_name: schema[table_name] for table_name in tables},
            "selection_method": "lexical_fallback",
            "model": None,
        }
