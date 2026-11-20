from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_]+", text.lower())


def select_relevant_tables(question: str, schema: dict[str, dict[str, Any]]) -> list[str]:
    if not question:
        return []

    tokens = set(tokenize(question))
    scores: dict[str, int] = defaultdict(int)

    for table_name, metadata in schema.items():
        table_tokens = {
            table_name.lower(),
            *table_name.lower().split("_"),
            *[column.lower() for column in metadata["columns"].keys()],
            *[
                token
                for column in metadata["columns"].keys()
                for token in column.lower().split("_")
            ],
        }
        matches = tokens & {token.lower() for token in table_tokens}
        scores[table_name] += len(matches)

        for column_name in metadata["columns"].keys():
            if column_name.lower() in tokens:
                scores[table_name] += 2

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    selected = [table for table, score in ranked if score > 0]
    return selected
