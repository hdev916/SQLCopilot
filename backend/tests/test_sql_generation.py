import pytest

from backend.app.schema_engine.sql_generation import (
    _extract_sql_candidate,
    _fallback_select,
    prepare_postgres_sql,
    _query_intent,
    _schema_for_model,
    _validate_query_intent,
    validate_sql,
)


RELEVANT_SCHEMA = {
    "users": {
        "columns": {
            "id": {"data_type": "integer"},
            "email": {"data_type": "text"},
        },
    }
}


def test_validate_sql_accepts_select_statements_only():
    sql = "SELECT id, email FROM users WHERE id = 1;"
    assert validate_sql(sql, RELEVANT_SCHEMA) == sql.strip()


def test_validate_sql_rejects_non_select_statements():
    with pytest.raises(ValueError, match="read-only SELECT"):
        validate_sql("DROP TABLE users;", RELEVANT_SCHEMA)


def test_validate_sql_rejects_multiple_statements():
    with pytest.raises(ValueError, match="single SQL statement"):
        validate_sql("SELECT id FROM users; DELETE FROM users;", RELEVANT_SCHEMA)


def test_validate_sql_rejects_unknown_schema_references():
    with pytest.raises(ValueError, match="unknown table"):
        validate_sql("SELECT id FROM secrets", RELEVANT_SCHEMA)

    with pytest.raises(ValueError, match="unknown column"):
        validate_sql("SELECT password_hash FROM users", RELEVANT_SCHEMA)


def test_prepare_postgres_sql_quotes_mixed_case_identifiers_and_qualifies_table():
    schema = {
        "User_details": {
            "schema": "public",
            "columns": {
                "User_Id": {"data_type": "integer"},
                "Muscle_trained": {"data_type": "text"},
            },
        }
    }

    prepared = prepare_postgres_sql(
        "SELECT User_Id, Muscle_trained FROM User_details",
        schema,
    )

    assert prepared == 'SELECT "User_Id", "Muscle_trained" FROM "public"."User_details"'


def test_prepare_postgres_sql_maps_lowercase_model_names_to_exact_schema_names():
    schema = {
        "User_details": {
            "schema": "public",
            "columns": {"User_Id": {"data_type": "integer"}},
        }
    }

    prepared = prepare_postgres_sql("SELECT user_id FROM user_details", schema)

    assert prepared == 'SELECT "User_Id" FROM "public"."User_details"'


def test_validate_sql_accepts_case_different_identifier_references():
    schema = {
        "User_Attendance": {
            "columns": {"User_Id": {"data_type": "uuid"}},
        }
    }

    assert validate_sql("SELECT user_id FROM user_attendance", schema)


def test_prepare_postgres_sql_quotes_qualified_join_references():
    schema = {
        "User_details": {
            "schema": "public",
            "columns": {"User_Id": {"data_type": "uuid"}},
        },
        "User_Attendance": {
            "schema": "public",
            "columns": {"User_Id": {"data_type": "uuid"}, "Attended": {}},
        },
    }

    prepared = prepare_postgres_sql(
        "SELECT User_details.User_Id, User_Attendance.Attended "
        "FROM User_details JOIN User_Attendance "
        "ON User_details.User_Id = User_Attendance.User_Id",
        schema,
    )

    assert '"User_details"."User_Id"' in prepared
    assert '"User_Attendance"."Attended"' in prepared


def test_prepare_postgres_sql_expands_star_without_sensitive_columns():
    schema = {
        "User_details": {
            "schema": "public",
            "columns": {
                "User_Id": {"data_type": "uuid"},
                "email": {"data_type": "text"},
                "password_hash": {"data_type": "text"},
            },
        }
    }

    prepared = prepare_postgres_sql("SELECT * FROM User_details", schema)

    assert prepared == (
        'SELECT "User_details"."User_Id", "User_details"."email" '
        'FROM "public"."User_details"'
    )
    assert validate_sql(prepared, schema)


def test_query_intent_removes_unrequested_ordering():
    sql = 'SELECT "User_Id" FROM "public"."User_details" ORDER BY created_at DESC'

    assert _validate_query_intent(sql, "Find users whose email contains gmail") == (
        'SELECT "User_Id" FROM "public"."User_details"'
    )


def test_extract_sql_candidate_removes_explanation_and_markdown():
    content = "Here is the query:\n```sql\nSELECT id FROM users;\n```"

    assert _extract_sql_candidate(content) == "SELECT id FROM users;"


def test_fallback_select_omits_sensitive_columns():
    schema = {
        "User_details": {
            "schema": "public",
            "columns": {
                "User_Id": {},
                "password_hash": {},
                "email": {},
            },
        }
    }

    sql = _fallback_select("show users", schema)

    assert sql == 'SELECT "User_Id", "email" FROM "public"."User_details" LIMIT 1000'
    assert "password_hash" not in sql
    assert validate_sql(prepare_postgres_sql(sql, schema), schema)


def test_schema_for_model_keeps_complete_catalog_without_database_defaults():
    schema = {
        "User_Attendance": {
            "schema": "public",
            "columns": {
                "User_Id": {"data_type": "uuid", "nullable": False},
                "Dated": {"data_type": "date", "default": "CURRENT_DATE"},
            },
            "foreign_keys": [
                {
                    "column": "User_Id",
                    "references_table": "User_details",
                    "references_column": "User_Id",
                    "constraint": "attendance_user_fkey",
                }
            ],
        }
    }

    model_schema = _schema_for_model(schema)

    assert model_schema == [
        {
            "schema": "public",
            "table": "User_Attendance",
            "columns": [
                {"name": "User_Id", "type": "uuid"},
                {"name": "Dated", "type": "date"},
            ],
            "foreign_keys": [
                {
                    "column": "User_Id",
                    "references_table": "User_details",
                    "references_column": "User_Id",
                }
            ],
        }
    ]


def test_query_intent_rejects_aggregate_when_request_asks_for_rows():
    sql = 'SELECT COUNT(*) FROM "public"."User_details"'

    with pytest.raises(ValueError, match="aggregation was not requested"):
        _validate_query_intent(sql, "Find users whose email contains gmail")


def test_query_intent_allows_explicit_count_request():
    sql = 'SELECT COUNT(*) FROM "public"."User_details"'

    assert _validate_query_intent(sql, "Count users whose email contains gmail") == sql


def test_query_intent_distinguishes_row_lookup_from_aggregation_and_ordering():
    assert _query_intent("Find users whose email contains gmail") == {
        "result_shape": "rows",
        "aggregation_requested": False,
        "ordering_requested": False,
    }
    assert _query_intent("Count the latest app versions") == {
        "result_shape": "aggregate",
        "aggregation_requested": True,
        "ordering_requested": True,
    }
