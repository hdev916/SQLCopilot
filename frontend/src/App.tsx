import { useEffect, useState } from 'react'
import './App.css'

const API_BASE = 'http://127.0.0.1:8000'

type HealthStatus = {
  status: string
  service: string
  database: string
  model: string
}

type SchemaTable = {
  name: string
  columns: string[]
  primary_keys?: string[]
}

type SchemaPreview = {
  status: string
  tables: SchemaTable[]
  message?: string
}

type GenerateResponse = {
  sql: string
  tables: string[]
  status: string
  model?: string
}

type ExecuteResponse = {
  columns: string[]
  rows: Record<string, unknown>[]
  row_count: number
  truncated: boolean
  execution_time_ms: number
}

type ChatMessage = {
  id: number
  role: 'user' | 'assistant'
  text: string
}

function App() {
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [schema, setSchema] = useState<SchemaPreview | null>(null)
  const [question, setQuestion] = useState('Show all active customers.')
  const [sql, setSql] = useState('SELECT 1;')
  const [result, setResult] = useState<ExecuteResponse | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 1,
      role: 'assistant',
      text: 'Ask a question about this database. I will select the relevant schema and draft a read-only SQL query.',
    },
  ])
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const [showChat, setShowChat] = useState(true)

  const loadBackend = async () => {
    try {
      const [healthResponse, schemaResponse] = await Promise.all([
        fetch(`${API_BASE}/health`),
        fetch(`${API_BASE}/api/schema/preview`),
      ])

      if (!healthResponse.ok || !schemaResponse.ok) {
        throw new Error('The backend or database is unavailable.')
      }

      setHealth((await healthResponse.json()) as HealthStatus)
      setSchema((await schemaResponse.json()) as SchemaPreview)
      setError('')
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not reach FastAPI.')
    }
  }

  useEffect(() => {
    void loadBackend()
  }, [])

  const appendMessage = (role: ChatMessage['role'], text: string) => {
    setMessages((current) => [
      ...current,
      { id: Date.now() + current.length, role, text },
    ])
  }

  const generateSql = async () => {
    const trimmedQuestion = question.trim()
    if (!trimmedQuestion) return

    setWorking(true)
    setError('')
    appendMessage('user', trimmedQuestion)

    try {
      const response = await fetch(
        `${API_BASE}/api/query/generate?question=${encodeURIComponent(trimmedQuestion)}`,
      )
      const payload = (await response.json()) as GenerateResponse & { detail?: string }

      if (!response.ok) {
        throw new Error(payload.detail || 'SQL generation failed.')
      }

      setSql(payload.sql)
      appendMessage(
        'assistant',
        `Drafted a query for ${payload.tables.length ? payload.tables.join(', ') : 'the relevant schema'}. Review it before execution.`,
      )
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : 'SQL generation failed.'
      setError(message)
      appendMessage('assistant', message)
    } finally {
      setWorking(false)
    }
  }

  const executeSql = async () => {
    if (!sql.trim()) return

    setWorking(true)
    setError('')

    try {
      const response = await fetch(`${API_BASE}/api/query/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sql }),
      })
      const payload = (await response.json()) as ExecuteResponse & { detail?: string }

      if (!response.ok) {
        throw new Error(payload.detail || 'Query execution failed.')
      }

      setResult(payload)
      appendMessage(
        'assistant',
        `Query executed successfully: ${payload.row_count} row${payload.row_count === 1 ? '' : 's'} in ${payload.execution_time_ms} ms.`,
      )
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : 'Query execution failed.'
      setError(message)
      appendMessage('assistant', message)
    } finally {
      setWorking(false)
    }
  }

  const tableNames = schema?.tables.map((table) => table.name) ?? []

  return (
    <div className="app-shell">
      <aside className="database-sidebar">
        <div className="brand-block">
          <div className="brand-mark">SQL</div>
          <div>
            <p className="eyebrow">Local workspace</p>
            <h1>SQL Code Pilot</h1>
          </div>
        </div>

        <div className="connection-card">
          <p className="section-label">Database connection</p>
          <strong>Local PostgreSQL</strong>
          <span className={health?.status === 'ok' ? 'status ok' : 'status'}>
            {health?.status ?? 'Checking'}
          </span>
        </div>

        <div className="schema-block">
          <div className="schema-heading">
            <p className="section-label">Live schema</p>
            <button type="button" className="icon-button" onClick={() => void loadBackend()}>
              Refresh
            </button>
          </div>
          {tableNames.length ? (
            <ul>
              {schema?.tables.map((table) => (
                <li key={table.name}>
                  <strong>{table.name}</strong>
                  <span>{table.columns.length} columns</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty-state">No live schema loaded.</p>
          )}
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div>
            <p className="eyebrow">AI SQL assistant</p>
            <h2>Query PostgreSQL locally</h2>
          </div>
          <button type="button" className="primary-button" onClick={() => setShowChat((value) => !value)}>
            {showChat ? 'Hide assistant' : 'Open assistant'}
          </button>
        </header>

        {error && <div className="error-banner">{error}</div>}

        <section className="editor-layout">
          <div className="panel editor-panel">
            <div className="panel-header">
              <span>SQL Editor</span>
              <span className="dimmed">Read-only execution</span>
            </div>
            <textarea
              className="sql-editor"
              value={sql}
              onChange={(event) => setSql(event.target.value)}
              spellCheck={false}
              aria-label="PostgreSQL SQL editor"
            />
            <div className="editor-actions">
              <button type="button" onClick={() => void executeSql()} disabled={working || !sql.trim()}>
                {working ? 'Working...' : 'Review & Run'}
              </button>
            </div>
          </div>

          <section className="panel results-panel">
            <div className="panel-header">
              <span>Query results</span>
              {result && (
                <span className="dimmed">
                  {result.row_count} rows • {result.execution_time_ms} ms
                  {result.truncated ? ' • limited' : ''}
                </span>
              )}
            </div>

            {result ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      {result.columns.map((column) => <th key={column}>{column}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((row, rowIndex) => (
                      <tr key={rowIndex}>
                        {result.columns.map((column) => (
                          <td key={column}>{String(row[column] ?? '')}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-results">Generated SQL can be reviewed and executed here.</div>
            )}
          </section>
        </section>
      </main>

      {showChat && (
        <aside className="assistant-attachment">
          <div className="assistant-header">
            <div>
              <p className="eyebrow">Assistant</p>
              <h2>Ask with SQL</h2>
            </div>
            <button type="button" className="icon-button" onClick={() => setShowChat(false)}>Close</button>
          </div>

          <div className="chat-history">
            {messages.map((message) => (
              <div key={message.id} className={`chat-message ${message.role}`}>
                {message.text}
              </div>
            ))}
          </div>

          <div className="chat-composer">
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  void generateSql()
                }
              }}
              placeholder="Ask a question about your database..."
              aria-label="Natural-language database question"
            />
            <button type="button" className="primary-button wide-button" onClick={() => void generateSql()} disabled={working || !question.trim()}>
              {working ? 'Generating...' : 'Generate SQL'}
            </button>
          </div>
        </aside>
      )}
    </div>
  )
}

export default App
