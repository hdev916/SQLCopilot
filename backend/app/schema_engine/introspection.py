from __future__ import annotations

from typing import Any

from sqlalchemy import text


def normalize_schema_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    schema: dict[str, dict[str, Any]] = {}

    for row in rows:
        table_name = row["table_name"]
        column_name = row["column_name"]
        table = schema.setdefault(
            table_name,
            {
                "schema": row.get("table_schema", "public"),
                "columns": {},
                "primary_keys": [],
                "foreign_keys": [],
            },
        )

        table["columns"].setdefault(
            column_name,
            {
                "data_type": row.get("data_type"),
                "nullable": row.get("is_nullable") != "NO",
                "default": row.get("column_default"),
                "ordinal_position": row.get("ordinal_position"),
                "identity": row.get("is_identity") == "YES",
            },
        )

        if row.get("is_primary_key"):
            pk_list = table["primary_keys"]
            if column_name not in pk_list:
                pk_list.append(column_name)

    return schema


def fetch_foreign_keys_from_database(engine: Any) -> list[dict[str, Any]]:
    query = text(
        """
        SELECT
                        source_table.relname AS table_name,
                        source_column.attname AS column_name,
                        target_table.relname AS foreign_table_name,
                        target_column.attname AS foreign_column_name,
                        fk.conname AS constraint_name
                FROM pg_constraint fk
                JOIN pg_class source_table ON source_table.oid = fk.conrelid
                JOIN pg_namespace source_schema ON source_schema.oid = source_table.relnamespace
                JOIN pg_class target_table ON target_table.oid = fk.confrelid
                JOIN pg_namespace target_schema ON target_schema.oid = target_table.relnamespace
                JOIN LATERAL unnest(fk.conkey) WITH ORDINALITY AS source_key(attnum, position) ON TRUE
                JOIN LATERAL unnest(fk.confkey) WITH ORDINALITY AS target_key(attnum, position)
                    ON target_key.position = source_key.position
                JOIN pg_attribute source_column
                    ON source_column.attrelid = source_table.oid
                 AND source_column.attnum = source_key.attnum
                JOIN pg_attribute target_column
                    ON target_column.attrelid = target_table.oid
                 AND target_column.attnum = target_key.attnum
                WHERE fk.contype = 'f'
                    AND source_schema.nspname = 'public'
                    AND target_schema.nspname = 'public'
                ORDER BY source_table.relname, fk.conname, source_key.position
        """
    )

    with engine.connect() as connection:
        result = connection.execute(query)
        rows = result.mappings().all()
    return [dict(row) for row in rows]


def add_foreign_keys(
    schema: dict[str, dict[str, Any]], foreign_keys: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    for foreign_key in foreign_keys:
        table_name = foreign_key["table_name"]
        if table_name not in schema:
            continue
        schema[table_name]["foreign_keys"].append(
            {
                "column": foreign_key["column_name"],
                "references_table": foreign_key["foreign_table_name"],
                "references_column": foreign_key["foreign_column_name"],
                "constraint": foreign_key["constraint_name"],
            }
        )
    return schema


def fetch_schema_from_database(engine: Any) -> list[dict[str, Any]]:
    query = text(
        """
        SELECT
            c.table_schema,
            c.table_name,
            c.column_name,
            c.data_type,
            c.is_nullable,
            c.column_default,
            c.is_identity,
            c.ordinal_position,
            EXISTS (
                SELECT 1
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                   AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_schema = c.table_schema
                  AND tc.table_name = c.table_name
                  AND kcu.column_name = c.column_name
            ) AS is_primary_key
        FROM information_schema.columns c
        WHERE c.table_schema = 'public'
        ORDER BY c.table_name, c.ordinal_position
        """
    )

    with engine.connect() as connection:
        result = connection.execute(query)
        rows = result.mappings().all()
    return [dict(row) for row in rows]
