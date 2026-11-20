from __future__ import annotations

import json
import os
from collections import deque
from typing import Any

import httpx

try:
    from backend.app.schema_engine.relevance import select_relevant_tables
except ModuleNotFoundError:  # pragma: no cover - allows running from backend folder
    from app.schema_engine.relevance import select_relevant_tables


class SchemaSelectionError(RuntimeError):
    pass


def parse_model_selection(
    response_text: str, schema: dict[str, dict[str, Any]]
) -> tuple[dict[str, list[str]], dict[str, str]]:
    try:
        response = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise SchemaSelectionError("Ollama returned invalid JSON for schema selection.") from exc

    if not isinstance(response, dict) or not isinstance(response.get("tables"), list):
        raise SchemaSelectionError("Ollama response must contain a tables array.")

    selected_columns: dict[str, list[str]] = {}
    reasons: dict[str, str] = {}
    for selection in response["tables"]:
        if not isinstance(selection, dict):
            continue
        requested_table_name = selection.get("name")
        if not isinstance(requested_table_name, str):
            continue
        table_name = next(
            (
                actual_name
                for actual_name in schema
                if actual_name.lower() == requested_table_name.lower()
            ),
            None,
        )
        if table_name is None:
            continue

        requested_columns = selection.get("columns", [])
        if not isinstance(requested_columns, list):
            continue
        known_columns = schema[table_name]["columns"]
        known_column_names = {
            column_name.lower(): column_name for column_name in known_columns
        }
        columns = list(dict.fromkeys(
            known_column_names[column.lower()]
            for column in requested_columns
            if isinstance(column, str) and column.lower() in known_column_names
        ))
        if not columns:
            columns = list(known_columns)
        selected_columns[table_name] = columns

        reason = selection.get("reason", "")
        if isinstance(reason, str):
            reasons[table_name] = reason[:300]

    return selected_columns, reasons


def connect_selected_tables(
    selected_tables: list[str], schema: dict[str, dict[str, Any]]
) -> list[str]:
    if not selected_tables:
        return []

    graph: dict[str, set[str]] = {table_name: set() for table_name in schema}
    for table_name, metadata in schema.items():
        for foreign_key in metadata.get("foreign_keys", []):
            referenced_table = foreign_key.get("references_table")
            if referenced_table in schema:
                graph[table_name].add(referenced_table)
                graph[referenced_table].add(table_name)

    included = list(dict.fromkeys(selected_tables))
    anchor = selected_tables[0]
    for target in selected_tables[1:]:
        queue = deque([(anchor, [anchor])])
        visited = {anchor}
        path: list[str] | None = None
        while queue:
            current, current_path = queue.popleft()
            if current == target:
                path = current_path
                break
            for neighbor in sorted(graph[current]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, [*current_path, neighbor]))
        if path:
            for table_name in path:
                if table_name not in included:
                    included.append(table_name)
    return included


def _schema_catalog(schema: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    catalog = []
    for table_name, metadata in schema.items():
        catalog.append(
            {
                "name": table_name,
                "columns": [
                    {"name": column_name, "type": column.get("data_type")}
                    for column_name, column in metadata["columns"].items()
                ],
                "primary_keys": metadata.get("primary_keys", []),
                "foreign_keys": metadata.get("foreign_keys", []),
            }
        )
    return catalog


async def select_relevant_schema(
    question: str, schema: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    if not question.strip():
        return {"tables": [], "schema": {}, "selection_method": "ollama_semantic"}

    model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:1.5b")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    catalog = _schema_catalog(schema)
    system_prompt = (
        "Select database tables and columns needed to answer the user's question. "
        "Use only names in the supplied schema. Interpret synonyms and intent. "
        "Include every table needed for joins and aggregation. If no schema objects "
        "can answer the question, return an empty tables array. Do not generate SQL."
    )
    user_prompt = json.dumps(
        {"question": question, "schema_catalog": catalog}, separators=(",", ":")
    )
    output_format = {
        "type": "object",
        "properties": {
            "tables": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "columns": {"type": "array", "items": {"type": "string"}},
                        "reason": {"type": "string"},
                    },
                    "required": ["name", "columns", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["tables"],
        "additionalProperties": False,
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                f"{base_url}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "format": output_format,
                    "options": {"temperature": 0},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
            response.raise_for_status()
            content = response.json()["message"]["content"]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise SchemaSelectionError(
            f"Could not get schema selection from Ollama at {base_url}. "
            "Check that Ollama is running and the configured model is available."
        ) from exc

    if not isinstance(content, str):
        raise SchemaSelectionError("Ollama returned an invalid schema-selection response.")

    selected_columns, reasons = parse_model_selection(content, schema)
    lexical_names = select_relevant_tables(question, schema)
    selected_names = list(dict.fromkeys([*selected_columns, *lexical_names]))
    for table_name in lexical_names:
        selected_columns.setdefault(table_name, list(schema[table_name]["columns"]))
    included_names = connect_selected_tables(selected_names, schema)
    relevant_schema: dict[str, Any] = {}
    for table_name in included_names:
        table = schema[table_name]
        if table_name in selected_columns:
            columns = selected_columns[table_name]
        else:
            columns = list(table["columns"])
        required_join_columns = {
            foreign_key["column"]
            for foreign_key in table.get("foreign_keys", [])
        }
        required_join_columns.update(
            foreign_key["references_column"]
            for source in schema.values()
            for foreign_key in source.get("foreign_keys", [])
            if foreign_key.get("references_table") == table_name
        )
        columns = list(dict.fromkeys([*columns, *required_join_columns]))
        relevant_schema[table_name] = {
            "schema": table.get("schema", "public"),
            "columns": {
                name: table["columns"][name]
                for name in columns
                if name in table["columns"]
            },
            "primary_keys": table.get("primary_keys", []),
            "foreign_keys": table.get("foreign_keys", []),
            "reason": reasons.get(
                table_name, "Included to connect selected tables through foreign keys."
            ),
        }

    return {
        "tables": included_names,
        "schema": relevant_schema,
        "selection_method": "ollama_semantic",
        "model": model,
    }