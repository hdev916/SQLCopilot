# Setup Guide

## Prerequisites

- Python 3.11+
- Node.js LTS
- PostgreSQL local instance
- Ollama local runtime
- VS Code or another editor

## Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Frontend

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

## Environment

Copy the example settings file and update values for the local environment:

```bash
copy config\settings.example.yaml config\settings.yaml
```

The current backend reads database and Ollama settings from environment variables. In PowerShell, set them in the shell that will run Uvicorn:

```powershell
$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_NAME = "your_database"
$env:DB_USER = "your_read_only_user"
$env:DB_PASSWORD = "your_local_password"
$env:OLLAMA_BASE_URL = "http://localhost:11434"
$env:OLLAMA_MODEL = "qwen2.5-coder:1.5b"
```

Install and start Ollama separately, then pull the configured model. The API's `/api/schema/relevant` endpoint uses Ollama for semantic table selection and returns HTTP 503 if Ollama or PostgreSQL is unavailable.

## Validation

- Backend health check: http://localhost:8000/health
- Frontend: http://localhost:5173
- Ollama: http://localhost:11434
