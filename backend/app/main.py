from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from backend.app.database.connection import create_db_engine, test_connection
    from backend.app.schema_engine.introspection import (
        add_foreign_keys,
        fetch_foreign_keys_from_database,
        fetch_schema_from_database,
        normalize_schema_rows,
    )
    from backend.app.schema_engine.ai_selector import SchemaSelectionError
    from backend.app.schema_engine.retrieval import build_relevant_schema
    from backend.app.schema_engine.sql_generation import (
        generate_sql,
        prepare_postgres_sql,
        validate_sql,
    )
    from backend.app.execution.controller import execute_read_only_query
except ModuleNotFoundError:  # pragma: no cover - allows running uvicorn from backend folder
    from app.database.connection import create_db_engine, test_connection
    from app.schema_engine.ai_selector import SchemaSelectionError
    from app.schema_engine.retrieval import build_relevant_schema
    from app.schema_engine.introspection import (
        add_foreign_keys,
        fetch_foreign_keys_from_database,
        fetch_schema_from_database,
        normalize_schema_rows,
    )
    from app.schema_engine.sql_generation import generate_sql, prepare_postgres_sql, validate_sql
    from app.execution.controller import execute_read_only_query

app = FastAPI(
    title="SQL Code Pilot API",
    version="0.1.0",
    description="Local schema-aware SQL assistant backend foundation.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    try:
        result = test_connection()
        return {
            "status": result["status"],
            "service": "sql-code-pilot-api",
            "database": result.get("database", "postgresql"),
            "model": "ollama-local",
        }
    except Exception:
        return {
            "status": "degraded",
            "service": "sql-code-pilot-api",
            "database": "not_configured",
            "model": "not_checked",
        }


@app.get("/api/db/test-connection")
async def db_test_connection() -> dict:
    try:
        return test_connection()
    except Exception as exc:  # pragma: no cover - defensive fallback
        raise HTTPException(
            status_code=503,
            detail="PostgreSQL connection failed. Check DB_HOST, DB_PORT, DB_USER, and DB_PASSWORD.",
        ) from exc


@app.get("/api/schema/preview")
async def schema_preview() -> dict:
    try:
        engine = create_db_engine()
        raw_rows = fetch_schema_from_database(engine)
        foreign_keys = fetch_foreign_keys_from_database(engine)
        schema = add_foreign_keys(normalize_schema_rows(raw_rows), foreign_keys)
        tables = [
            {
                "name": table_name,
                "columns": list(table["columns"].keys()),
                "primary_keys": table.get("primary_keys", []),
                "foreign_keys": table.get("foreign_keys", []),
            }
            for table_name, table in schema.items()
        ]
        return {
            "database": "postgresql",
            "status": "ready",
            "tables": tables,
            "message": "Live PostgreSQL metadata introspection is active.",
        }
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not read the PostgreSQL schema. Check the database connection and permissions.",
        ) from exc


@app.get("/api/schema/relevant")
async def schema_relevant(question: str = Query(..., description="Natural language request to match against schema.")) -> dict:
    try:
        engine = create_db_engine()
        raw_rows = fetch_schema_from_database(engine)
        foreign_keys = fetch_foreign_keys_from_database(engine)
        schema = add_foreign_keys(normalize_schema_rows(raw_rows), foreign_keys)
        selection = await build_relevant_schema(question, schema)
        return {
            "question": question,
            "relevant_tables": selection["tables"],
            "schema": selection["schema"],
            "selection_method": selection["selection_method"],
            "model": selection.get("model"),
        }
    except SchemaSelectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not retrieve PostgreSQL schema for semantic selection. Check DB_HOST, DB_PORT, DB_NAME, DB_USER, and DB_PASSWORD.",
        ) from exc


@app.get("/api/query/test")
async def query_test() -> dict:
    return {
        "sql": "SELECT 1;",
        "explanation": "Smoke test for the local backend and SQL pipeline scaffold.",
        "status": "ok",
    }


class ExecuteQueryRequest(BaseModel):
    sql: str = Field(..., min_length=1)


@app.get("/api/query/generate")
async def query_generate(question: str = Query(..., description="Natural-language question to translate into SQL.")) -> dict:
    try:
        engine = create_db_engine()
        raw_rows = fetch_schema_from_database(engine)
        foreign_keys = fetch_foreign_keys_from_database(engine)
        schema = add_foreign_keys(normalize_schema_rows(raw_rows), foreign_keys)
        selection = await build_relevant_schema(question, schema)
        sql = await generate_sql(question, schema)
        validated = validate_sql(sql, schema)
        return {
            "question": question,
            "sql": validated,
            "tables": selection["tables"],
            "schema_scope": "full",
            "selection_method": selection["selection_method"],
            "model": selection.get("model"),
            "status": "ready",
        }
    except (SchemaSelectionError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not generate SQL from the PostgreSQL schema. Check the database connection and Ollama model runtime.",
        ) from exc


@app.post("/api/query/execute")
async def query_execute(request: ExecuteQueryRequest) -> dict:
    try:
        engine = create_db_engine()
        raw_rows = fetch_schema_from_database(engine)
        foreign_keys = fetch_foreign_keys_from_database(engine)
        schema = add_foreign_keys(normalize_schema_rows(raw_rows), foreign_keys)
        relevant_schema = {
            table_name: table
            for table_name, table in schema.items()
            if any(
                table_name.lower() in request.sql.lower()
                for table_name in schema
            )
        }
        prepared_sql = prepare_postgres_sql(request.sql, relevant_schema or schema)
        validated = validate_sql(prepared_sql, relevant_schema or schema)
        return execute_read_only_query(engine, validated)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not execute the approved query. Check the database connection and permissions.",
        ) from exc
