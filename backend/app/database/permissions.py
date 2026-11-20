from __future__ import annotations


class ReadOnlyPolicy:
    allowed_statements = {"SELECT"}
    blocked_statements = {"INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE"}

    @classmethod
    def validate_statement(cls, statement: str) -> bool:
        normalized = statement.strip().upper()
        if not normalized:
            return False
        if ";" in normalized:
            return False
        first_keyword = normalized.split()[0] if normalized.split() else ""
        return first_keyword in cls.allowed_statements
