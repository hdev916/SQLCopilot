from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
from sqlglot import exp, parse, parse_one

_SENSITIVE_IDENTIFIER_PATTERN = re.compile(
    r"(?:password|passwd|token|secret|credential|api[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)


def _strip_code_fence(sql: str) -> str:
    cleaned = sql.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:sql|postgresql)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    return cleaned.strip()


def _extract_sql_candidate(content: str) -> str:
    cleaned = _strip_code_fence(content)
    match = re.search(r"\b(?:SELECT|WITH)\b", cleaned, flags=re.IGNORECASE)
    if match:
        cleaned = cleaned[match.start():]
    cleaned = re.split(r"\s*```", cleaned, maxsplit=1)[0]
    return cleaned.strip()


def _quote_identifier(identifier: str) -> exp.Identifier:
    return exp.Identifier(this=identifier, quoted=True)


def _schema_for_model(schema: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "schema": table.get("schema", "public"),
            "table": table_name,
            "columns": [
                {"name": column_name, "type": metadata.get("data_type")}
                for column_name, metadata in table.get("columns", {}).items()
            ],
            "foreign_keys": [
                {
                    "column": foreign_key.get("column"),
                    "references_table": foreign_key.get("references_table"),
                    "references_column": foreign_key.get("references_column"),
                }
                for foreign_key in table.get("foreign_keys", [])
            ],
        }
        for table_name, table in schema.items()
    ]


def _query_intent(question: str) -> dict[str, Any]:
    aggregate_requested = bool(
        re.search(
            r"\b(count|how many|number of|total|sum|average|avg|mean|maximum|minimum)\b",
            question,
            flags=re.IGNORECASE,
        )
    )
    ordering_requested = bool(
        re.search(
            r"\b(latest|earliest|newest|oldest|sort|order|rank|ranking|top|bottom|ascending|descending)\b",
            question,
            flags=re.IGNORECASE,
        )
    )
    return {
        "result_shape": "aggregate" if aggregate_requested else "rows",
        "aggregation_requested": aggregate_requested,
        "ordering_requested": ordering_requested,
    }


def _fallback_select(question: str, schema: dict[str, Any]) -> str:
    try:
        from backend.app.schema_engine.relevance import select_relevant_tables
    except ModuleNotFoundError:  # pragma: no cover - allows running from backend folder
        from app.schema_engine.relevance import select_relevant_tables

    candidates = select_relevant_tables(question, schema)
    ordered_tables = [*candidates, *(name for name in schema if name not in candidates)]

    for table_name in ordered_tables:
        if _SENSITIVE_IDENTIFIER_PATTERN.search(table_name):
            continue
        table = schema[table_name]
        columns = [
            column_name
            for column_name in table.get("columns", {})
            if not _SENSITIVE_IDENTIFIER_PATTERN.search(column_name)
        ]
        if not columns:
            continue

        schema_name = table.get("schema", "public")
        quoted_schema = schema_name.replace('"', '""')
        quoted_table = table_name.replace('"', '""')
        quoted_columns = ", ".join(
            '"' + column_name.replace('"', '""') + '"' for column_name in columns
        )
        return (
            f'SELECT {quoted_columns} FROM "{quoted_schema}"."{quoted_table}" '
            "LIMIT 1000"
        )

    raise ValueError("No table with non-sensitive columns is available for fallback SQL.")


def _expand_select_stars(parsed: exp.Expression, schema: dict[str, Any]) -> None:
    table_lookup = {name.lower(): name for name in schema}

    def collect_tables(node: exp.Expression | None) -> list[exp.Table]:
        if node is None or isinstance(node, exp.Select):
            return []
        if isinstance(node, exp.Table):
            return [node]
        return [
            table
            for child in node.iter_expressions()
            for table in collect_tables(child)
        ]

    for select in parsed.find_all(exp.Select):
        source_tables = collect_tables(select.args.get("from"))
        source_tables.extend(
            table
            for join in select.args.get("joins", [])
            for table in collect_tables(join)
        )
        expanded_expressions: list[exp.Expression] = []

        for projection in select.expressions:
            if isinstance(projection, exp.Star):
                requested_table = None
            elif isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star):
                requested_table = projection.table
            else:
                expanded_expressions.append(projection)
                continue

            matching_tables = []
            for table in source_tables:
                actual_name = table_lookup.get(table.name.lower())
                if actual_name is None:
                    continue
                alias = table.args.get("alias")
                alias_identifier = alias.this if alias else None
                alias_name = alias_identifier.this if alias_identifier else None
                if requested_table and requested_table.lower() not in {
                    table.name.lower(),
                    (alias_name or "").lower(),
                }:
                    continue
                matching_tables.append((table, actual_name, alias_identifier))

            if not matching_tables:
                raise ValueError("Could not safely expand SELECT * against the supplied schema.")

            for table, actual_name, alias_identifier in matching_tables:
                qualifier = alias_identifier.copy() if alias_identifier else _quote_identifier(actual_name)
                for column_name in schema[actual_name].get("columns", {}):
                    if _SENSITIVE_IDENTIFIER_PATTERN.search(column_name):
                        continue
                    expanded_expressions.append(
                        exp.Column(
                            this=_quote_identifier(column_name),
                            table=qualifier.copy(),
                        )
                    )

        select.set("expressions", expanded_expressions)


def prepare_postgres_sql(sql: str, relevant_schema: dict[str, Any]) -> str:
    """Map model identifiers to exact PostgreSQL names and qualify public tables."""
    cleaned = _strip_code_fence(sql)
    parsed = parse_one(cleaned, read="postgres")
    table_lookup = {
        table_name.lower(): table_name for table_name in relevant_schema
    }
    column_lookup: dict[str, str] = {}
    for table in relevant_schema.values():
        for column_name in table.get("columns", {}):
            column_lookup.setdefault(column_name.lower(), column_name)

    for table in parsed.find_all(exp.Table):
        actual_name = table_lookup.get(table.name.lower(), table.name)
        if actual_name in relevant_schema:
            table.set("this", _quote_identifier(actual_name))
            if not table.db:
                schema_name = relevant_schema[actual_name].get("schema", "public")
                table.set("db", _quote_identifier(schema_name))

    _expand_select_stars(parsed, relevant_schema)

    for column in parsed.find_all(exp.Column):
        if column.name == "*":
            if column.table:
                actual_table = table_lookup.get(column.table.lower(), column.table)
                if actual_table in relevant_schema:
                    column.set("table", _quote_identifier(actual_table))
            continue
        actual_name = column_lookup.get(column.name.lower(), column.name)
        if actual_name != column.name or any(char.isupper() for char in actual_name):
            column.set("this", _quote_identifier(actual_name))
        if column.table:
            actual_table = table_lookup.get(column.table.lower(), column.table)
            if actual_table in relevant_schema:
                column.set("table", _quote_identifier(actual_table))

    return parsed.sql(dialect="postgres")


def validate_sql(sql: str, relevant_schema: dict[str, Any] | None = None) -> str:
    if not isinstance(sql, str):
        raise TypeError("SQL query must be a string.")

    cleaned = _strip_code_fence(sql)
    if not cleaned:
        raise ValueError("SQL query is empty.")

    forbidden_types = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Create,
        exp.Alter,
        exp.Drop,
        exp.Merge,
        exp.Copy,
    )

    first_keyword = cleaned.lstrip().split(None, 1)[0].upper().rstrip(";") if cleaned.strip() else ""
    forbidden_keywords = {"INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE", "MERGE", "COPY"}
    if first_keyword in forbidden_keywords:
        raise ValueError("Only read-only SELECT statements are allowed.")

    try:
        statements = parse(cleaned, read="postgres")
    except Exception as exc:  # pragma: no cover - intentionally surfaced as validation error
        raise ValueError("SQL could not be parsed as a valid PostgreSQL SELECT statement.") from exc

    statements = [statement for statement in statements if statement is not None]
    if len(statements) != 1:
        raise ValueError("Only a single SQL statement is allowed.")

    parsed = statements[0]
    if isinstance(parsed, forbidden_types):
        raise ValueError("Only read-only SELECT statements are allowed.")

    if not isinstance(parsed, (exp.Select, exp.Subquery, exp.With)):
        raise ValueError("Only read-only SELECT statements are allowed.")

    if relevant_schema:
        allowed_tables = {table_name.lower() for table_name in relevant_schema}
        unknown_tables = {
            table.name
            for table in parsed.find_all(exp.Table)
            if table.name and table.name.lower() not in allowed_tables
        }
        if unknown_tables:
            raise ValueError(
                "SQL references unknown table(s): " + ", ".join(sorted(unknown_tables))
            )

        allowed_columns: set[str] = set()
        for table_name, table in relevant_schema.items():
            allowed_columns.update(
                column.lower() for column in table.get("columns", {})
            )
            allowed_columns.update(
                column.lower() for column in table.get("primary_keys", [])
            )

        unknown_columns = {
            column.name
            for column in parsed.find_all(exp.Column)
            if column.name
            and column.name != "*"
            and column.name.lower() not in allowed_columns
        }
        if unknown_columns:
            raise ValueError(
                "SQL references unknown column(s): " + ", ".join(sorted(unknown_columns))
            )

    return cleaned


def _validate_query_intent(sql: str, question: str) -> str:
    intent = _query_intent(question)
    parsed = parse_one(sql, read="postgres")
    if not intent["aggregation_requested"] and next(parsed.find_all(exp.AggFunc), None) is not None:
        raise ValueError(
            "Generated SQL contains an aggregation when aggregation was not requested."
        )
    if not intent["ordering_requested"] and parsed.args.get("order"):
        parsed.set("order", None)
        return parsed.sql(dialect="postgres")
    return sql


async def generate_sql(
    question: str,
    relevant_schema: dict[str, Any],
    *,
    model: str | None = None,
    base_url: str | None = None,
) -> str:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("A natural-language question is required to generate SQL.")
    if not isinstance(relevant_schema, dict) or not relevant_schema:
        raise ValueError("A non-empty relevant schema is required to generate SQL.")

    resolved_model = model or os.getenv("OLLAMA_MODEL", "qwen2.5-coder:1.5b")
    resolved_base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")

    system_prompt = (
        "Translate the user's question into one PostgreSQL SELECT statement. "
        "The question is the task; the schema is reference data only. Never summarize or describe the schema. "
        "Preserve the requested operation, filters, grouping, and ordering. Use COUNT for count requests and "
        "ORDER BY for latest, earliest, or ranking requests; do not replace these with a generic row listing. "
        "For find, show, or list requests, return matching rows and do not use aggregate functions. "
        "Only aggregate when the user explicitly asks for a count, total, sum, or average. "
        "Do not add ORDER BY unless the user asks for an ordering or latest/earliest results. "
        "Use only tables and columns in the complete schema catalog. Qualify tables with their schema and "
        "quote identifiers containing uppercase letters. Return only SQL, with no markdown or explanation."
    )
    user_prompt = json.dumps(
        {
            "question": question,
            "query_intent": _query_intent(question),
            "schema": _schema_for_model(relevant_schema),
        },
        separators=(",", ":"),
    )

    async def request_model(messages: list[dict[str, str]]) -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{resolved_base_url}/api/chat",
                json={
                    "model": resolved_model,
                    "stream": False,
                    "options": {"temperature": 0, "num_predict": 512, "num_ctx": 8192},
                    "messages": messages,
                },
            )
            response.raise_for_status()
            content = response.json()["message"]["content"]
            if not isinstance(content, str):
                raise RuntimeError("Ollama returned an invalid SQL-generation response.")
            return content

    try:
        content = await request_model(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Could not generate SQL from Ollama at {resolved_base_url}. "
            "Check that Ollama is running and the configured model is available."
        ) from exc

    try:
        prepared_sql = prepare_postgres_sql(_extract_sql_candidate(content), relevant_schema)
        return _validate_query_intent(validate_sql(prepared_sql, relevant_schema), question)
    except Exception as first_error:
        repair_prompt = json.dumps(
            {
                "question": question,
                "query_intent": _query_intent(question),
                "schema": _schema_for_model(relevant_schema),
                "invalid_sql": content,
            },
            separators=(",", ":"),
        )
        repair_system_prompt = (
            "Repair the invalid SQL for PostgreSQL while preserving the user's requested operation and filters. "
            "Return only one complete SELECT statement. Use only tables and columns in the supplied schema. "
            "If the question asks to find, show, or list rows, do not use COUNT or other aggregate functions. "
            "Use aggregates only when explicitly requested, and do not add unrequested ordering. "
            "Do not summarize the schema, explain the repair, or use markdown."
        )
        try:
            repaired_content = await request_model(
                [
                    {"role": "system", "content": repair_system_prompt},
                    {"role": "user", "content": repair_prompt},
                ]
            )
            repaired_sql = prepare_postgres_sql(
                _extract_sql_candidate(repaired_content), relevant_schema
            )
            return _validate_query_intent(
                validate_sql(repaired_sql, relevant_schema), question
            )
        except Exception as repair_error:
            fallback_sql = _fallback_select(question, relevant_schema)
            try:
                return validate_sql(
                    prepare_postgres_sql(fallback_sql, relevant_schema), relevant_schema
                )
            except Exception as fallback_error:
                raise ValueError(
                    "The model returned SQL that could not be normalized or repaired for PostgreSQL."
                ) from fallback_error
