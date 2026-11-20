# SQL Model Benchmark Summary

Model: `qwen2.5-coder:1.5b`
Prompts: 38
HTTP 200 / 400: 38 / 0
Syntax acceptance: 1.000
Intent score: 0.567
Table relevance: 1.000
Latency average / median / p95: 28092.87 / 26517.85 / 33636.89 ms
Lexical fallback uses: 1
Safety failures: 5
Ambiguity failures: 5

## Category Scores

| Category | Count | HTTP 200 | Syntax | Intent | Relevance | Avg ms | Median ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| aggregation | 5 | 5 | 1.000 | 0.760 | 1.000 | 32016.19 | 23752.94 | 51995.28 |
| ambiguity | 5 | 5 | 1.000 | 0.000 | 1.000 | 28571.82 | 29325.87 | 35317.58 |
| basic | 5 | 5 | 1.000 | 1.000 | 1.000 | 27014.66 | 25375.87 | 31819.45 |
| best-first | 3 | 3 | 1.000 | 0.833 | 1.000 | 27994.57 | 27584.01 | 31907.28 |
| date | 5 | 5 | 1.000 | 0.467 | 1.000 | 29419.77 | 30422.8 | 32875.32 |
| filter | 5 | 5 | 1.000 | 1.000 | 1.000 | 25466.65 | 24079.3 | 30806.93 |
| relationship | 5 | 5 | 1.000 | 0.583 | 1.000 | 25070.51 | 22896.52 | 30491.58 |
| safety | 5 | 5 | 1.000 | 0.000 | 1.000 | 29149.45 | 30371.76 | 31420.39 |

## Recommended Improvements

1. Reject destructive, update, multi-statement, and unknown-table intent before Ollama generates SQL.
2. Add a clarification contract for underspecified terms and return HTTP 422 or a structured clarification response.
3. Add deterministic SQL templates for counts, date ranges, first-N rows, joins, and group-by queries.
4. Normalize result ordering for ranking prompts and remove fallback-generated generic row lists.
5. Execute only read-only statements against PostgreSQL; generation success is not execution validation.

Raw reports: `backend/benchmark_results/model_batch_*.json` and `.csv`.