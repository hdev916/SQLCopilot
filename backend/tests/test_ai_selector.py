import asyncio

from backend.app.schema_engine import retrieval
from backend.app.schema_engine.ai_selector import (
    connect_selected_tables,
    parse_model_selection,
    SchemaSelectionError,
)


def test_model_selection_discards_unknown_tables_and_columns():
    schema = {
        "customers": {
            "columns": {"id": {}, "name": {}, "created_at": {}},
            "primary_keys": ["id"],
            "foreign_keys": [],
        }
    }

    selected, reasons = parse_model_selection(
        '{"tables":[{"name":"customers","columns":["name","made_up"],'
        '"reason":"Customer names match the request."},'
        '{"name":"invented_table","columns":["id"],"reason":"unknown"}]}',
        schema,
    )

    assert selected == {"customers": ["name"]}
    assert reasons == {"customers": "Customer names match the request."}


def test_table_connection_adds_shortest_foreign_key_join_path():
    schema = {
        "customers": {
            "foreign_keys": [],
        },
        "orders": {
            "foreign_keys": [
                {"references_table": "customers"},
                {"references_table": "regions"},
            ],
        },
        "regions": {
            "foreign_keys": [],
        },
        "audit_events": {
            "foreign_keys": [
                {"references_table": "customers"},
            ],
        },
    }

    assert connect_selected_tables(["customers", "regions"], schema) == [
        "customers",
        "regions",
        "orders",
    ]


def test_model_selection_matches_mixed_case_table_and_column_names():
    schema = {
        "User_Attendance": {
            "columns": {"User_Id": {}, "Dated": {}},
            "primary_keys": [],
            "foreign_keys": [],
        }
    }

    selected, _ = parse_model_selection(
        '{"tables":[{"name":"user_attendance","columns":["user_id"],"reason":"attendance"}]}',
        schema,
    )

    assert selected == {"User_Attendance": ["User_Id"]}


def test_retrieval_uses_lexical_fallback_when_semantic_selection_fails(monkeypatch):
    schema = {
        "User_Attendance": {"columns": {"User_Id": {}, "Dated": {}}},
        "accounts": {"columns": {"id": {}, "email": {}}},
    }

    async def fail_selection(question, supplied_schema):
        raise SchemaSelectionError("Ollama is temporarily unavailable")

    monkeypatch.setattr(retrieval, "select_relevant_schema", fail_selection)
    result = asyncio.run(
        retrieval.build_relevant_schema("show attendance", schema)
    )

    assert result["tables"] == ["User_Attendance"]
    assert result["schema"] == {"User_Attendance": schema["User_Attendance"]}
    assert result["selection_method"] == "lexical_fallback"
    assert result["model"] is None