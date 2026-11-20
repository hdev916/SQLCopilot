# SQL Code Pilot

A local, schema-aware SQL assistant built with:

- FastAPI backend
- React + TypeScript frontend
- PostgreSQL metadata extraction
- Ollama-based local SQL generation
- SQL validation and safe execution gates

# SQL Code Pilot

A local, schema-aware SQL assistant built with FastAPI, React, PostgreSQL, Ollama, and SQLGlot.

## Backend

Create the local configuration file once:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and enter your PostgreSQL password. The backend loads that file automatically.

Start the backend with one command:

```powershell
.\backend\.venv\Scripts\python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

## Frontend

In a second terminal:

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1
```

Open http://127.0.0.1:5173.

## Current capabilities

- PostgreSQL connection testing and live schema introspection
- Ollama-assisted schema selection and SQL generation
- SQLGlot read-only validation
- Approved-query execution with timeouts and row limits
- React SQL editor, assistant attachment, and result grid
