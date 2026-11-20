from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path


RESULT_DIR = Path("backend/benchmark_results")


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * pct
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return round(ordered[lower] * (1 - fraction) + ordered[upper] * fraction, 2)


def avg(rows: list[dict], field: str) -> float:
    if not rows:
        return 0.0
    return round(sum(row[field] for row in rows) / len(rows), 3)


def main() -> None:
    rows: list[dict] = []
    for path in sorted(RESULT_DIR.glob("model_batch_*.json")):
        rows.extend(json.loads(path.read_text(encoding="utf-8")))

    category_rows: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        category_rows[row["category"]].append(row)

    categories = {}
    for category, items in sorted(category_rows.items(), key=lambda item: item[0]):
        latencies = [row["latency_ms"] for row in items]
        categories[category] = {
            "count": len(items),
            "http_200": sum(row["status"] == 200 for row in items),
            "http_400": sum(row["status"] == 400 for row in items),
            "syntax_avg": avg(items, "syntax_score"),
            "intent_avg": avg(items, "intent_score"),
            "relevance_avg": avg(items, "relevance_score"),
            "latency_avg_ms": round(statistics.mean(latencies), 2),
            "latency_median_ms": round(statistics.median(latencies), 2),
            "latency_p95_ms": percentile(latencies, 0.95),
            "lexical_fallback_count": sum(row.get("selection_method") == "lexical_fallback" for row in items),
        }

    latencies = [row["latency_ms"] for row in rows]
    report = {
        "model": "qwen2.5-coder:1.5b",
        "total_prompts": len(rows),
        "http_200": sum(row["status"] == 200 for row in rows),
        "http_400": sum(row["status"] == 400 for row in rows),
        "syntax_avg": avg(rows, "syntax_score"),
        "intent_avg": avg(rows, "intent_score"),
        "relevance_avg": avg(rows, "relevance_score"),
        "latency_avg_ms": round(statistics.mean(latencies), 2),
        "latency_median_ms": round(statistics.median(latencies), 2),
        "latency_p95_ms": percentile(latencies, 0.95),
        "lexical_fallback_count": sum(row.get("selection_method") == "lexical_fallback" for row in rows),
        "category": categories,
        "failed_safety_count": sum(row["category"] == "safety" and row["intent_score"] == 0 for row in rows),
        "failed_ambiguity_count": sum(row["category"] == "ambiguity" and row["intent_score"] == 0 for row in rows),
    }

    json_path = RESULT_DIR / "benchmark_summary.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# SQL Model Benchmark Summary",
        "",
        f"Model: `qwen2.5-coder:1.5b`",
        f"Prompts: {report['total_prompts']}",
        f"HTTP 200 / 400: {report['http_200']} / {report['http_400']}",
        f"Syntax acceptance: {report['syntax_avg']:.3f}",
        f"Intent score: {report['intent_avg']:.3f}",
        f"Table relevance: {report['relevance_avg']:.3f}",
        f"Latency average / median / p95: {report['latency_avg_ms']} / {report['latency_median_ms']} / {report['latency_p95_ms']} ms",
        f"Lexical fallback uses: {report['lexical_fallback_count']}",
        f"Safety failures: {report['failed_safety_count']}",
        f"Ambiguity failures: {report['failed_ambiguity_count']}",
        "",
        "## Category Scores",
        "",
        "| Category | Count | HTTP 200 | Syntax | Intent | Relevance | Avg ms | Median ms | P95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for category, metrics in categories.items():
        lines.append(
            f"| {category} | {metrics['count']} | {metrics['http_200']} | "
            f"{metrics['syntax_avg']:.3f} | {metrics['intent_avg']:.3f} | "
            f"{metrics['relevance_avg']:.3f} | {metrics['latency_avg_ms']} | "
            f"{metrics['latency_median_ms']} | {metrics['latency_p95_ms']} |"
        )

    lines.extend([
        "",
        "## Recommended Improvements",
        "",
        "1. Reject destructive, update, multi-statement, and unknown-table intent before Ollama generates SQL.",
        "2. Add a clarification contract for underspecified terms and return HTTP 422 or a structured clarification response.",
        "3. Add deterministic SQL templates for counts, date ranges, first-N rows, joins, and group-by queries.",
        "4. Normalize result ordering for ranking prompts and remove fallback-generated generic row lists.",
        "5. Execute only read-only statements against PostgreSQL; generation success is not execution validation.",
        "",
        "Raw reports: `backend/benchmark_results/model_batch_*.json` and `.csv`.",
    ])

    markdown_path = RESULT_DIR / "benchmark_summary.md"
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
