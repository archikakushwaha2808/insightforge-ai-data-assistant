import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Send, Bot, User, Sparkles, Plus, MessageSquare, Mic, MicOff, Menu, X } from 'lucide-react'
import client from '../api/client'
import ChartCard from '../components/ChartCard'
import SqlResultTable from '../components/SqlResultTable'

// --- Voice input (Web Speech API) -------------------------------------------
// User-only speech-to-text: the transcript lands in the input box for the
// user to review/edit and send normally. The AI's response stays 100% text —
// no speech synthesis, no "read aloud", nothing added on the output side.
const SpeechRecognitionCtor = typeof window !== 'undefined'
  ? (window.SpeechRecognition || window.webkitSpeechRecognition)
  : null

function useVoiceInput(onTranscript) {
  const [listening, setListening] = useState(false)
  const [unsupportedNotice, setUnsupportedNotice] = useState('')
  const recognitionRef = useRef(null)

  const toggle = useCallback(() => {
    if (!SpeechRecognitionCtor) {
      setUnsupportedNotice("Voice input isn't supported in this browser. Please use Chrome or another supported browser.")
      return
    }
    if (listening) {
      recognitionRef.current?.stop()
      return
    }
    setUnsupportedNotice('')
    const recognition = new SpeechRecognitionCtor()
    recognition.lang = 'en-US'
    recognition.interimResults = true
    recognition.continuous = false
    let finalTranscript = ''
    recognition.onresult = (event) => {
      let interim = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const chunk = event.results[i][0].transcript
        if (event.results[i].isFinal) finalTranscript += chunk
        else interim += chunk
      }
      onTranscript(finalTranscript + interim)
    }
    recognition.onerror = (event) => {
      setListening(false)
      if (event.error === 'not-allowed' || event.error === 'permission-denied') {
        setUnsupportedNotice('Microphone permission was denied. You can still type your question.')
      }
    }
    recognition.onend = () => setListening(false)
    recognitionRef.current = recognition
    try {
      recognition.start()
      setListening(true)
    } catch {
      setListening(false)
    }
  }, [listening, onTranscript])

  useEffect(() => () => recognitionRef.current?.stop(), [])

  return { listening, toggle, unsupportedNotice, supported: !!SpeechRecognitionCtor }
}

// --- Session grouping (Today / Yesterday / Earlier), ChatGPT-style ---------
function groupSessions(sessions) {
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1)
  const groups = { Today: [], Yesterday: [], Earlier: [] }
  for (const s of sessions) {
    const d = new Date(s.updated_at || s.created_at)
    const day = new Date(d); day.setHours(0, 0, 0, 0)
    if (day.getTime() === today.getTime()) groups.Today.push(s)
    else if (day.getTime() === yesterday.getTime()) groups.Yesterday.push(s)
    else groups.Earlier.push(s)
  }
  return Object.entries(groups).filter(([, list]) => list.length > 0)
}

function MessageBubble({ m }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}
    >
      <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0
        ${m.role === 'user' ? 'bg-surface border border-border' : 'bg-signal-gradient'}`}>
        {m.role === 'user' ? <User size={14} /> : <Bot size={14} className="text-black" />}
      </div>
      <div className={`max-w-[80%] ${m.role === 'user' ? 'items-end' : ''} flex flex-col gap-3`}>
        {(m.tables && m.tables.length) || m.table ? (
          <>
            {(m.tables && m.tables.length ? m.tables : [m.table]).map((tbl, ti, arr) => (
              <div key={ti} className="w-full max-w-lg">
                {arr.length > 1 && (
                  <div className="text-[10px] font-mono uppercase tracking-wide text-muted/70 mb-1 px-1">
                    Query {tbl?.query_number || ti + 1} of {arr.length}
                  </div>
                )}
                <SqlResultTable table={tbl} />
              </div>
            ))}
            {((m.charts && m.charts.length) ? m.charts : (m.chart ? [m.chart] : [])).map((ch, ci) => (
              <div key={ci} className="w-full max-w-md">
                <ChartCard chart={ch} />
              </div>
            ))}
            {m.content && (
              <div className="w-full max-w-lg">
                <div className="text-[10px] font-mono uppercase tracking-wide text-muted/70 mb-1 px-1">Summary</div>
                <div className="px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap bg-surface/50 border border-border">
                  {m.content}
                </div>
              </div>
            )}
          </>
        ) : (
          <>
            <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap
              ${m.role === 'user' ? 'bg-signal-cyan/10 border border-signal-cyan/20' : 'bg-surface/50 border border-border'}`}>
              {m.content}
            </div>
            {((m.charts && m.charts.length) ? m.charts : (m.chart ? [m.chart] : [])).map((ch, ci) => (
              <div key={ci} className="w-full max-w-md">
                <ChartCard chart={ch} />
              </div>
            ))}
          </>
        )}
      </div>
    </motion.div>
  )
}

export default function ChatPage() {
  const [datasets, setDatasets] = useState([])
  const [selectedId, setSelectedId] = useState(null)

  const [sessions, setSessions] = useState([])
  const [selectedSessionId, setSelectedSessionId] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const scrollRef = useRef()

  const voice = useVoiceInput(setInput)

  useEffect(() => {
    client.get('/datasets/').then((res) => {
      let data = Array.isArray(res.data)
          ? res.data
          : Array.isArray(res.data?.datasets)
            ? res.data.datasets
            : []

        // Use the dataset already selected/uploaded in Workspace
        // when the production dataset list is empty/stale.
        if (!data.length) {
          const savedId = localStorage.getItem('insightforge-last-dataset-id')
          const savedName = localStorage.getItem('insightforge-last-dataset-name')

          if (savedId && savedName) {
            data = [{
              id: Number(savedId),
              filename: savedName
            }]
          }
        }

        setDatasets(data)
      if (res.data.length) setSelectedId(res.data[0].id)
    })
  }, [])

  const loadSessions = useCallback(async (datasetId, selectFirst = true) => {
    const res = await client.get(`/chat/${datasetId}/sessions`)
    setSessions(res.data)
    if (selectFirst) {
      setSelectedSessionId(res.data.length ? res.data[0].id : null)
      if (!res.data.length) setMessages([])
    }
    return res.data
  }, [])

  useEffect(() => {
    if (selectedId) loadSessions(selectedId, true)
  }, [selectedId, loadSessions])

  useEffect(() => {
    if (!selectedSessionId) return
    client.get(`/chat/sessions/${selectedSessionId}/history`).then((res) => setMessages(res.data))
  }, [selectedSessionId])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sending])

  const startNewChat = async () => {
    if (!selectedId) return
    const res = await client.post(`/chat/${selectedId}/sessions`)
    setSessions((s) => [res.data, ...s])
    setSelectedSessionId(res.data.id)
    setMessages([])
    setInput('')
  }

  const sendMessage = async () => {
    if (!input.trim() || !selectedId) return
    const text = input
    setMessages((m) => [...m, { role: 'user', content: text }])
    setInput('')
    setSending(true)
    try {
      let sessionId = selectedSessionId
      if (!sessionId) {
        const created = await client.post(`/chat/${selectedId}/sessions`)
        sessionId = created.data.id
        setSelectedSessionId(sessionId)
        setSessions((s) => [created.data, ...s])
      }
      const res = await client.post(`/chat/sessions/${sessionId}/message`, { message: text })
      setMessages((m) => [...m, {
        role: 'assistant', content: res.data.reply,
        chart: res.data.chart, charts: res.data.charts,
        table: res.data.table, tables: res.data.tables,
      }])
      // Keep the sidebar's title/ordering in sync (auto-titled from the
      // first message, most-recently-active conversation floats to top).
      setSessions((s) => {
        const updated = s.map((sess) => sess.id === sessionId
          ? { ...sess, title: res.data.session_title, updated_at: new Date().toISOString() }
          : sess)
        return [...updated].sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))
      })
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Unknown error'
      setMessages((m) => [...m, { role: 'assistant', content: `Error: ${detail}` }])
    } finally {
      setSending(false)
    }
  }

  if (!datasets.length) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-24 text-center">
        <Bot size={40} className="mx-auto mb-4 text-signal-cyan" />
        <h1 className="font-display text-2xl font-semibold mb-2">No datasets yet</h1>
        <p className="text-muted">Upload a dataset in the Workspace first, then come back to chat about it.</p>
      </div>
    )
  }

  const grouped = groupSessions(sessions)

  return (
    <div className="max-w-7xl mx-auto px-4 md:px-6 py-6 flex gap-4 h-[calc(100vh-88px)]">
      {/* Sidebar: New Chat + grouped conversation history, ChatGPT-style */}
      <AnimatePresence initial={false}>
        {sidebarOpen && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 260, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            className="shrink-0 overflow-hidden border-r border-border pr-4 flex flex-col"
          >
            <div className="w-[244px] flex flex-col h-full">
              <button
                onClick={startNewChat}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-border hover:border-signal-cyan text-sm font-medium transition-colors mb-4"
              >
                <Plus size={15} /> New Chat
              </button>

              <select
                value={selectedId || ''}
                onChange={(e) => setSelectedId(Number(e.target.value))}
                className="mb-4 px-3 py-2 rounded-lg bg-surface/50 border border-border text-xs outline-none focus:border-signal-cyan"
              >
                {(Array.isArray(datasets) ? datasets : []).map((d) => <option key={d.id} value={d.id}>{d.filename}</option>)}
              </select>

              <div className="flex-1 overflow-y-auto hide-scrollbar space-y-4">
                {grouped.length === 0 && (
                  <p className="text-xs text-muted px-1">No conversations yet — start one below.</p>
                )}
                {grouped.map(([label, list]) => (
                  <div key={label}>
                    <p className="text-[10px] font-mono uppercase tracking-wider text-muted/70 px-1 mb-1.5">{label}</p>
                    <div className="space-y-0.5">
                      {list.map((s) => (
                        <button
                          key={s.id}
                          onClick={() => setSelectedSessionId(s.id)}
                          className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm truncate transition-colors
                            ${s.id === selectedSessionId ? 'bg-signal-cyan/10 text-ink border border-signal-cyan/30' : 'hover:bg-surface/50 text-muted border border-transparent'}`}
                        >
                          <MessageSquare size={13} className="shrink-0" />
                          <span className="truncate">{s.title}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSidebarOpen((o) => !o)}
              className="w-8 h-8 rounded-lg flex items-center justify-center border border-border hover:border-signal-cyan transition-colors mr-1"
              aria-label="Toggle chat history"
            >
              {sidebarOpen ? <X size={14} /> : <Menu size={14} />}
            </button>
            <Sparkles size={18} className="text-signal-cyan" />
            <h1 className="font-display text-lg font-semibold">Data Assistant</h1>
          </div>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-5 pr-2 hide-scrollbar">
          {messages.length === 0 && (
            <div className="text-center text-muted py-16 space-y-1">
              <p>Ask anything — "what's driving the highest values?", "show me a trend chart", "what's the average revenue by region as a SQL query?"</p>
              <p className="text-xs">Looking for the full interactive dashboard? Check the <span className="text-signal-cyan">Dashboard</span> tab in Workspace.</p>
            </div>
          )}
          {messages.map((m, i) => <MessageBubble key={i} m={m} />)}
          {sending && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-signal-gradient flex items-center justify-center shrink-0">
                <Bot size={14} className="text-black" />
              </div>
              <div className="px-4 py-3 rounded-2xl bg-surface/50 border border-border flex gap-1">
                {[0, 1, 2].map((i) => (
                  <span key={i} className="w-1.5 h-1.5 rounded-full bg-signal-cyan animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
                ))}
              </div>
            </div>
          )}
        </div>

        {voice.unsupportedNotice && (
          <p className="mt-3 text-xs text-signal-magenta">{voice.unsupportedNotice}</p>
        )}
        {voice.listening && (
          <p className="mt-3 text-xs text-signal-cyan flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-signal-cyan animate-pulse" /> Listening…
          </p>
        )}

        <div className="mt-3 flex items-center gap-3">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
            placeholder="Ask about your data…"
            className="flex-1 px-5 py-3.5 rounded-full bg-surface/50 border border-border outline-none focus:border-signal-cyan transition-colors text-sm"
          />
          <button
            onClick={voice.toggle}
            aria-label={voice.listening ? 'Stop voice input' : 'Start voice input'}
            title={voice.supported ? 'Voice input' : "Voice input isn't supported in this browser"}
            className={`w-12 h-12 rounded-full flex items-center justify-center border transition-colors shrink-0
              ${voice.listening ? 'bg-signal-magenta/10 border-signal-magenta text-signal-magenta' : 'border-border hover:border-signal-cyan'}`}
          >
            {voice.listening ? <MicOff size={16} /> : <Mic size={16} />}
          </button>
          <button
            onClick={sendMessage}
            disabled={sending || !input.trim()}
            className="w-12 h-12 rounded-full bg-signal-gradient flex items-center justify-center hover:opacity-90 disabled:opacity-40 transition-opacity shrink-0"
          >
            <Send size={16} className="text-black" />
          </button>
        </div>
      </div>
    </div>
  )
}
