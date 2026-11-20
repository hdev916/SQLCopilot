# SQL Code Pilot Architecture

SQL Code Pilot is a local-first natural-language-to-SQL application built with:

- FastAPI for application APIs and workflow control
- PostgreSQL for authoritative schema metadata and query execution
- SQLAlchemy and Psycopg for database connectivity
- Ollama for local model inference
- SQLGlot for SQL parsing and AST-based validation
- React and TypeScript for the user interface
- Monaco Editor for reviewing and editing SQL

## Request flow

```text
User question
	-> FastAPI receives the request
	-> backend loads the cached PostgreSQL schema catalogue
	-> local model selects likely tables and columns by meaning
	-> backend validates the selected identifiers and expands required FK links
	-> local model generates SQL using the question and verified relevant schema
	-> backend parses and validates the SQL
	-> UI shows the query for user review and editing
	-> backend executes only after approval, using read-only database controls
	-> UI displays the real result rows and execution metadata
```

The model proposes schema selections and SQL; it does not connect to PostgreSQL, receive credentials, or execute queries. The backend remains responsible for database access, verification, policy enforcement, and execution.

## AI-assisted schema selection

The backend extracts schema metadata from PostgreSQL because it is the source of truth. The schema catalogue includes table and column names, data types, primary keys, foreign keys, and optionally database descriptions. It does not include credentials or table row data.

The local model uses the user's wording and the catalogue to select likely tables and columns. This lets it relate concepts such as "purchase amount" to schema names such as `total_amount`, rather than requiring exact keyword matches. The model returns structured identifiers, a short rationale, and an ambiguity or confidence signal. The backend checks that every returned schema identifier exists before using it. SQL generation receives the complete live schema, so semantic selection is informative and does not prevent the model from using another valid table when the question requires it.

After selection, the backend uses foreign-key metadata to add necessary join paths for selection display. SQL generation receives the complete verified schema and remains free to choose any valid table or relationship. The validator still rejects identifiers that do not exist in PostgreSQL.

For a small or medium schema, the initial selector can receive a compact catalogue of table and column metadata. For a large schema, inexpensive retrieval may shortlist candidates before the model ranks them. In that design, lexical matching is only a recall aid, not the final semantic decision. Embeddings are deferred unless evaluation shows they improve selection quality enough to justify their extra complexity.

Schema selection and SQL generation may initially be separate model calls for easier testing and clearer failures. They use the same local model runtime. Latency and accuracy measurements will determine whether a combined call is preferable for smaller schemas.

## Safety boundaries

- The model never receives database credentials or query result data as schema context.
- The backend validates model-selected tables and columns against live metadata.
- SQLGlot parses SQL and checks statement structure; parser success alone is not a security guarantee.
- The initial execution policy permits read-only queries only.
- A dedicated PostgreSQL read-only role and read-only transactions enforce the database-side boundary.
- Statement timeouts, lock timeouts, approved schemas, and row limits constrain execution.
- Generated SQL is shown to the user and is not executed until explicitly approved.

## Implementation milestones

### 1. Local foundation

Verify Python, Node.js, PostgreSQL, and Ollama on the development machine. Run the compact local model and record a baseline for latency and resource use. Keep the model replaceable and do not fine-tune for the MVP.

### 2. PostgreSQL connectivity and schema catalogue

Implement connection configuration, connection testing, catalog introspection, normalized metadata, foreign-key graph extraction, schema caching, and refresh. The backend must expose actual tables, columns, keys, and relationships; sample fallback schema must never be presented as live database metadata.

Acceptance: a configured PostgreSQL database returns its actual schema and relationships through the API, and a connection failure is reported with an appropriate error status and message.

### 3. AI-assisted schema selection and SQL generation

Add an Ollama client and structured schema-selection response. Validate returned table and column identifiers, expand foreign-key join paths in the backend, then send only verified relevant schema to SQL generation. Ask for clarification when schema or intent is insufficient instead of inventing identifiers.

Acceptance: reviewed questions select semantically relevant tables, invalid model-proposed identifiers are rejected, and SQL generation uses only the verified schema context.

### 4. SQL validation and controlled execution

Use SQLGlot for parsing and AST inspection, verify referenced schema objects, block multiple statements and non-read-only operations, and add PostgreSQL `EXPLAIN` validation. Execute through a dedicated read-only role with timeouts and row limits, only after explicit user approval.

Acceptance: destructive or invalid SQL is rejected before execution, and database permissions independently prevent writes.

### 5. Frontend workflow

Connect the database, schema explorer, assistant, editable SQL editor, validation, execution, and results UI to real backend APIs. Replace static schema and result examples with live responses. Keep generated SQL editable and require a user action to execute it.

Acceptance: a user can ask a question, inspect and edit generated SQL, approve execution, and see actual query results.

### 6. Reliability and local operations

Add structured logs without credentials or sensitive result data, persistent query history, schema refresh behavior, configuration validation, health checks, bounded request handling, and graceful failure behavior. Keep the model configurable through application settings.

### 7. Evaluation and deployment

Test against real PostgreSQL schemas and a reviewed set of natural-language questions. Measure schema-selection accuracy, SQL correctness, latency, and safety behavior. Compare the chosen compact model with an alternative before selecting the default. Run the frontend, API, and Ollama locally without cloud LLM dependencies.

## Evaluation cases

- Semantic synonyms: user wording differs from table and column names.
- Multi-table questions: model identifies the needed tables and backend supplies valid FK paths.
- Ambiguous and unsupported questions: request clarification rather than fabricate schema.
- Invalid model identifiers: backend rejects tables or columns absent from PostgreSQL metadata.
- Safety: writes, multiple statements, and oversized result sets are blocked or constrained.
- Scale: compare direct compact-catalogue selection with candidate-shortlist-plus-model selection.
