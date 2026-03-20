import { useState, useRef, useEffect, useCallback } from 'react'

// ─── Styles ────────────────────────────────────────────────────────────────

const css = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #0c0c0e;
    --surface:   #141416;
    --border:    #232328;
    --muted:     #3a3a42;
    --text:      #e8e6e1;
    --text-dim:  #7a7880;
    --accent:    #c8b89a;
    --accent-lo: #c8b89a18;
    --user-bg:   #1a1a1f;
    --bot-bg:    #111113;
    --danger:    #e05c5c;
    --mono:      'DM Mono', monospace;
    --serif:     'DM Serif Display', serif;
    --radius:    12px;
    --transition: 180ms ease;
  }

  html, body, #root {
    height: 100%;
    background: var(--bg);
    color: var(--text);
    font-family: var(--mono);
    font-size: 14px;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }

  /* ── Layout ── */
  .shell {
    display: grid;
    grid-template-columns: 260px 1fr;
    grid-template-rows: 100vh;
    height: 100vh;
    overflow: hidden;
  }

  /* ── Sidebar ── */
  .sidebar {
    background: var(--surface);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    padding: 24px 16px;
    gap: 24px;
    overflow-y: auto;
  }

  .logo {
    font-family: var(--serif);
    font-size: 22px;
    color: var(--accent);
    letter-spacing: -0.5px;
    padding: 0 8px;
  }

  .logo span {
    display: block;
    font-family: var(--mono);
    font-size: 10px;
    color: var(--text-dim);
    font-weight: 300;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-top: 2px;
  }

  .divider {
    height: 1px;
    background: var(--border);
  }

  .sidebar-label {
    font-size: 10px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--text-dim);
    padding: 0 8px;
  }

  .flow-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .flow-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 8px;
    cursor: pointer;
    transition: background var(--transition);
    border: 1px solid transparent;
  }

  .flow-item:hover { background: var(--accent-lo); }
  .flow-item.active {
    background: var(--accent-lo);
    border-color: var(--accent);
  }

  .flow-dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: var(--muted);
    flex-shrink: 0;
    transition: background var(--transition);
  }
  .flow-item.active .flow-dot { background: var(--accent); }

  .flow-name {
    font-size: 13px;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .status-bar {
    margin-top: auto;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    border-radius: 8px;
    background: var(--bg);
    border: 1px solid var(--border);
    font-size: 11px;
    color: var(--text-dim);
  }

  .status-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--muted);
    flex-shrink: 0;
  }
  .status-dot.ok  { background: #5cb85c; box-shadow: 0 0 6px #5cb85c88; }
  .status-dot.err { background: var(--danger); }
  .status-dot.checking { animation: pulse 1s infinite; background: var(--accent); }

  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

  /* ── Main pane ── */
  .main {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }

  .topbar {
    border-bottom: 1px solid var(--border);
    padding: 16px 28px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--bg);
    flex-shrink: 0;
  }

  .topbar-title {
    font-family: var(--serif);
    font-size: 16px;
    color: var(--text);
  }

  .topbar-meta {
    font-size: 11px;
    color: var(--text-dim);
    letter-spacing: 1px;
    text-transform: uppercase;
  }

  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 10px;
    letter-spacing: 1px;
    text-transform: uppercase;
    background: var(--accent-lo);
    color: var(--accent);
    border: 1px solid var(--accent);
  }

  /* ── Messages ── */
  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 32px 28px;
    display: flex;
    flex-direction: column;
    gap: 20px;
    scroll-behavior: smooth;
  }

  .messages::-webkit-scrollbar { width: 4px; }
  .messages::-webkit-scrollbar-track { background: transparent; }
  .messages::-webkit-scrollbar-thumb { background: var(--muted); border-radius: 2px; }

  .msg {
    display: flex;
    gap: 14px;
    max-width: 720px;
    animation: fadeSlide 240ms ease both;
  }

  @keyframes fadeSlide {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  .msg.user { align-self: flex-end; flex-direction: row-reverse; }
  .msg.bot  { align-self: flex-start; }

  .avatar {
    width: 32px; height: 32px;
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 12px;
    flex-shrink: 0;
    border: 1px solid var(--border);
    font-family: var(--mono);
  }

  .msg.user .avatar { background: var(--accent); color: var(--bg); border-color: var(--accent); }
  .msg.bot  .avatar { background: var(--surface); color: var(--accent); }

  .bubble {
    padding: 12px 16px;
    border-radius: var(--radius);
    font-size: 13.5px;
    line-height: 1.65;
    max-width: 580px;
    word-break: break-word;
  }

  .msg.user .bubble {
    background: var(--user-bg);
    border: 1px solid var(--border);
    border-top-right-radius: 4px;
    color: var(--text);
  }

  .msg.bot .bubble {
    background: var(--bot-bg);
    border: 1px solid var(--border);
    border-top-left-radius: 4px;
    color: var(--text);
  }

  .bubble.error { border-color: var(--danger); color: var(--danger); }

  .typing-dots {
    display: flex; gap: 4px; align-items: center; padding: 4px 0;
  }
  .typing-dots span {
    width: 5px; height: 5px;
    border-radius: 50%;
    background: var(--accent);
    animation: dot 1.2s infinite;
  }
  .typing-dots span:nth-child(2) { animation-delay: .2s; }
  .typing-dots span:nth-child(3) { animation-delay: .4s; }
  @keyframes dot { 0%,80%,100%{opacity:.2;transform:scale(1)} 40%{opacity:1;transform:scale(1.3)} }

  .empty-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    color: var(--text-dim);
    text-align: center;
  }

  .empty-icon {
    font-size: 40px;
    opacity: .3;
    margin-bottom: 8px;
  }

  .empty-title {
    font-family: var(--serif);
    font-size: 22px;
    color: var(--text);
    opacity: .5;
  }

  /* ── Input bar ── */
  .input-area {
    border-top: 1px solid var(--border);
    padding: 16px 28px 20px;
    background: var(--bg);
    flex-shrink: 0;
  }

  .input-row {
    display: flex;
    gap: 10px;
    align-items: flex-end;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 8px 8px 8px 16px;
    transition: border-color var(--transition);
  }

  .input-row:focus-within { border-color: var(--accent); }

  textarea {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    color: var(--text);
    font-family: var(--mono);
    font-size: 13.5px;
    line-height: 1.6;
    resize: none;
    min-height: 24px;
    max-height: 160px;
    overflow-y: auto;
  }

  textarea::placeholder { color: var(--text-dim); }

  .send-btn {
    width: 36px; height: 36px;
    border-radius: 8px;
    border: none;
    background: var(--accent);
    color: var(--bg);
    cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    transition: opacity var(--transition), transform var(--transition);
    font-size: 16px;
  }

  .send-btn:disabled { opacity: .3; cursor: default; transform: none !important; }
  .send-btn:not(:disabled):hover { opacity: .85; transform: scale(1.05); }

  .hint {
    margin-top: 8px;
    font-size: 11px;
    color: var(--text-dim);
    text-align: center;
    letter-spacing: .5px;
  }

  /* ── Flow ID config panel ── */
  .config-panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px 24px;
    margin: 24px 28px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .config-title {
    font-family: var(--serif);
    font-size: 16px;
    color: var(--accent);
  }

  .config-desc {
    font-size: 12px;
    color: var(--text-dim);
    line-height: 1.7;
  }

  .config-input-row {
    display: flex; gap: 8px;
  }

  input[type="text"] {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 12px;
    color: var(--text);
    font-family: var(--mono);
    font-size: 13px;
    outline: none;
    transition: border-color var(--transition);
  }

  input[type="text"]:focus { border-color: var(--accent); }
  input[type="text"]::placeholder { color: var(--text-dim); }

  .btn-primary {
    padding: 8px 16px;
    background: var(--accent);
    color: var(--bg);
    border: none;
    border-radius: 8px;
    font-family: var(--mono);
    font-size: 12px;
    cursor: pointer;
    white-space: nowrap;
    transition: opacity var(--transition);
  }

  .btn-primary:hover { opacity: .85; }
`

// ─── API helpers ───────────────────────────────────────────────────────────

async function langflowLogin() {
  const resp = await fetch('/api/v1/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'admin', password: 'testpass123' })
  })
  if (!resp.ok) throw new Error('Login failed')
  const data = await resp.json()
  return data.access_token
}

async function langflowRun(flowId, token, message) {
  const resp = await fetch(`/api/v1/run/${flowId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
      input_value: message,
      input_type: 'chat',
      output_type: 'chat'
    })
  })
  if (!resp.ok) throw new Error(`Flow error: ${resp.status}`)
  const data = await resp.json()

  // Extract text from Langflow response structure
  try {
    return data.outputs[0].outputs[0].results.message.text
  } catch {
    return JSON.stringify(data, null, 2)
  }
}

async function checkHealth() {
  const resp = await fetch('/api/v1/version')
  return resp.ok
}

// ─── Component ────────────────────────────────────────────────────────────

export default function App() {
  const [messages, setMessages]     = useState([])
  const [input, setInput]           = useState('')
  const [loading, setLoading]       = useState(false)
  const [token, setToken]           = useState(null)
  const [health, setHealth]         = useState('checking')  // 'checking' | 'ok' | 'err'
  const [flowId, setFlowId]         = useState('')
  const [flowIdDraft, setFlowIdDraft] = useState('')
  const [configured, setConfigured] = useState(false)
  const messagesEndRef              = useRef(null)
  const textareaRef                 = useRef(null)

  // Scroll to bottom on new message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Health check on mount + periodically
  useEffect(() => {
    const check = async () => {
      try {
        const ok = await checkHealth()
        setHealth(ok ? 'ok' : 'err')
      } catch {
        setHealth('err')
      }
    }
    check()
    const id = setInterval(check, 30_000)
    return () => clearInterval(id)
  }, [])

  // Auth on mount
  useEffect(() => {
    langflowLogin()
      .then(setToken)
      .catch(() => setHealth('err'))
  }, [])

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || loading || !token || !configured) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', text }])
    setLoading(true)

    try {
      const reply = await langflowRun(flowId, token, text)
      setMessages(prev => [...prev, { role: 'bot', text: reply }])
    } catch (err) {
      setMessages(prev => [...prev, { role: 'bot', text: err.message, error: true }])
    } finally {
      setLoading(false)
      textareaRef.current?.focus()
    }
  }, [input, loading, token, flowId, configured])

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  const autoResize = (e) => {
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }

  const applyFlowId = () => {
    if (flowIdDraft.trim()) {
      setFlowId(flowIdDraft.trim())
      setConfigured(true)
      setMessages([])
    }
  }

  const MOCK_FLOWS = [
    { id: 'echo_chat',       name: 'Echo Chat',       active: configured && flowId === 'echo_chat' },
    { id: 'webhook_logger',  name: 'Webhook Logger',  active: false },
  ]

  const statusLabel = health === 'ok' ? 'Langflow connected'
                    : health === 'err' ? 'Cannot reach Langflow'
                    : 'Checking…'

  return (
    <>
      <style>{css}</style>
      <div className="shell">
        {/* ── Sidebar ── */}
        <aside className="sidebar">
          <div className="logo">
            FlowDesk
            <span>AI Assistant</span>
          </div>

          <div className="divider" />

          <div className="sidebar-label">Flows</div>
          <div className="flow-list">
            {MOCK_FLOWS.map(f => (
              <div
                key={f.id}
                className={`flow-item ${f.active ? 'active' : ''}`}
                onClick={() => {
                  setFlowIdDraft(f.id)
                  setFlowId(f.id)
                  setConfigured(true)
                  setMessages([])
                }}
              >
                <div className="flow-dot" />
                <div className="flow-name">{f.name}</div>
              </div>
            ))}
          </div>

          <div className="status-bar" style={{ marginTop: 'auto' }}>
            <div className={`status-dot ${health}`} />
            {statusLabel}
          </div>
        </aside>

        {/* ── Main ── */}
        <main className="main">
          <div className="topbar">
            <div className="topbar-title">
              {configured ? (flowId || 'Chat') : 'Configure a flow to begin'}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span className="topbar-meta">v1.8.1</span>
              <span className="badge">Public</span>
            </div>
          </div>

          {/* Flow ID config prompt */}
          {!configured && (
            <div className="config-panel">
              <div className="config-title">Connect a flow</div>
              <div className="config-desc">
                Enter a Langflow flow ID (UUID) or use the sidebar to pick a preset.<br />
                The bootstrapper creates two public flows on startup — check <code>/data/flow_ids.json</code> for their IDs.
              </div>
              <div className="config-input-row">
                <input
                  type="text"
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                  value={flowIdDraft}
                  onChange={e => setFlowIdDraft(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && applyFlowId()}
                />
                <button className="btn-primary" onClick={applyFlowId}>Connect</button>
              </div>
            </div>
          )}

          {/* Messages */}
          <div className="messages">
            {configured && messages.length === 0 && !loading && (
              <div className="empty-state">
                <div className="empty-icon">◈</div>
                <div className="empty-title">Ready</div>
                <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                  Send a message to begin the session
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                <div className="avatar">{m.role === 'user' ? 'U' : 'AI'}</div>
                <div className={`bubble ${m.error ? 'error' : ''}`}>{m.text}</div>
              </div>
            ))}

            {loading && (
              <div className="msg bot">
                <div className="avatar">AI</div>
                <div className="bubble">
                  <div className="typing-dots">
                    <span /><span /><span />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="input-area">
            <div className="input-row">
              <textarea
                ref={textareaRef}
                rows={1}
                placeholder={configured ? 'Type a message…' : 'Connect a flow first'}
                value={input}
                disabled={!configured || loading}
                onChange={e => { setInput(e.target.value); autoResize(e) }}
                onKeyDown={onKeyDown}
              />
              <button
                className="send-btn"
                disabled={!input.trim() || loading || !configured}
                onClick={send}
                title="Send (Enter)"
              >
                ↑
              </button>
            </div>
            <div className="hint">Enter to send · Shift+Enter for newline</div>
          </div>
        </main>
      </div>
    </>
  )
}
