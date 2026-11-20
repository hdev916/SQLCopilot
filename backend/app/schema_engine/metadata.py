from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ColumnMetadata:
    name: str
    data_type: str | None
    nullable: bool = True
    default: str | None = None
    ordinal_position: int | None = None
    identity: bool = False


@dataclass
class TableMetadata:
    name: str
    schema: str = "public"
    columns: dict[str, ColumnMetadata] = field(default_factory=dict)
    primary_keys: list[str] = field(default_factory=list)


@dataclass
class SchemaMetadata:
    tables: dict[str, TableMetadata] = field(default_factory=dict)

    def add_table(self, table: TableMetadata) -> None:
        self.tables[table.name] = table

    def to_dict(self) -> dict[str, Any]:
        return {
            table_name: {
                "schema": table.schema,
                "columns": {col_name: col.__dict__ for col_name, col in table.columns.items()},
                "primary_keys": table.primary_keys,
            }
            for table_name, table in self.tables.items()
        }
