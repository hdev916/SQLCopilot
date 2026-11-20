from backend.app.schema_engine.introspection import normalize_schema_rows


def test_normalize_schema_rows_collects_tables_columns_and_relations():
    rows = [
        {
            "table_schema": "public",
            "table_name": "users",
            "column_name": "id",
            "data_type": "integer",
            "is_nullable": "NO",
            "column_default": "nextval('users_id_seq'::regclass)",
            "is_identity": "YES",
            "ordinal_position": 1,
            "is_primary_key": True,
        },
        {
            "table_schema": "public",
            "table_name": "users",
            "column_name": "email",
            "data_type": "text",
            "is_nullable": "NO",
            "column_default": None,
            "is_identity": "NO",
            "ordinal_position": 2,
            "is_primary_key": False,
        },
        {
            "table_schema": "public",
            "table_name": "orders",
            "column_name": "id",
            "data_type": "integer",
            "is_nullable": "NO",
            "column_default": "nextval('orders_id_seq'::regclass)",
            "is_identity": "YES",
            "ordinal_position": 1,
            "is_primary_key": True,
        },
        {
            "table_schema": "public",
            "table_name": "orders",
            "column_name": "user_id",
            "data_type": "integer",
            "is_nullable": "NO",
            "column_default": None,
            "is_identity": "NO",
            "ordinal_position": 2,
            "is_primary_key": False,
        },
        {
            "table_schema": "public",
            "table_name": "orders",
            "column_name": "user_id",
            "data_type": "integer",
            "is_nullable": "NO",
            "column_default": None,
            "is_identity": "NO",
            "ordinal_position": 2,
            "is_primary_key": False,
        },
    ]

    schema = normalize_schema_rows(rows)

    assert "users" in schema
    assert "orders" in schema
    assert schema["users"]["columns"]["id"]["data_type"] == "integer"
    assert schema["orders"]["columns"]["user_id"]["nullable"] is False
    assert schema["users"]["primary_keys"] == ["id"]
    assert schema["orders"]["primary_keys"] == ["id"]
