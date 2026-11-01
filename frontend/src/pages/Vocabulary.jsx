import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { STATUSES, statusMeta } from '../statuses.js'

export default function Vocabulary({ onChanged, notify }) {
  const [words, setWords] = useState([])
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const cancelRef = useRef(false)

  const load = useCallback(async () => {
    setError('')
    try {
      const data = await api.words({ q: query.trim(), status: status === 'all' ? '' : status })
      setWords(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [query, status])

  useEffect(() => {
    const delay = query.trim() ? 240 : 0
    const timer = setTimeout(load, delay)
    return () => clearTimeout(timer)
  }, [load, query])

  async function save(id, patch) {
    setBusyId(id)
    try {
      const updated = await api.patchWord(id, patch)
      setWords((list) =>
        list.map((item) =>
          item.id === id
            ? { ...item, ...updated, context_count: updated.context_count ?? item.context_count }
            : item,
        ),
      )
      onChanged?.()
      return updated
    } catch (err) {
      notify(err.message, 'error')
      return null
    } finally {
      setBusyId(null)
    }
  }

  function commitTranslation(word, value) {
    if (cancelRef.current) {
      cancelRef.current = false
      setEditing(null)
      return
    }
    const trimmed = value.trim()
    setEditing(null)
    if (!trimmed || trimmed === (word.translation || '').trim()) return
    save(word.id, { translation: trimmed })
  }

  async function removeWord(word) {
    if (!window.confirm(`Remove “${word.lemma}” and its history?`)) return
    try {
      await api.deleteWord(word.id)
      setWords((list) => list.filter((item) => item.id !== word.id))
      onChanged?.()
      notify('Word removed')
    } catch (err) {
      notify(err.message, 'error')
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1 className="page-title">Vocabulary</h1>
          <p className="page-sub">{words.length} words</p>
        </div>
        <div className="head-actions">
          <a className="btn ghost small" href={api.ankiUrl} download="ru-reader-anki.txt">
            Export Anki
          </a>
        </div>
      </header>

      <div className="card toolbar">
        <input
          className="input"
          value={query}
          placeholder="Search lemma or translation"
          onChange={(event) => setQuery(event.target.value)}
        />
        <select className="select" value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="all">All statuses</option>
          {STATUSES.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </div>

      {loading ? <div className="state-card">Loading words…</div> : null}
      {!loading && error ? <div className="state-card hint error">{error}</div> : null}
      {!loading && !error && words.length === 0 ? (
        <div className="state-card">No words here yet. Open a lesson and tap a word.</div>
      ) : null}

      <div className="word-list">
        {words.map((word) => {
          const meta = statusMeta(word.status)
          return (
            <div key={word.id} className="card word-row">
              <span className="dot" style={{ background: meta.color }} />
              <div className="word-lemma">
                <strong>{word.lemma}</strong>
                {word.surface && word.surface !== word.lemma ? <span className="hint-inline"> · {word.surface}</span> : null}
                {word.grammar ? <p className="meta-line">{word.grammar}</p> : null}
              </div>
              <div className="word-translation">
                {editing?.id === word.id ? (
                  <input
                    className="input translation-edit"
                    autoFocus
                    defaultValue={editing.value}
                    onFocus={() => {
                      cancelRef.current = false
                    }}
                    onBlur={(event) => commitTranslation(word, event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') event.currentTarget.blur()
                      if (event.key === 'Escape') {
                        cancelRef.current = true
                        setEditing(null)
                      }
                    }}
                  />
                ) : (
                  <button
                    type="button"
                    className="translation-value"
                    onClick={() => setEditing({ id: word.id, value: word.translation || '' })}
                  >
                    {word.translation || 'Add translation'}
                  </button>
                )}
              </div>
              <div className="word-actions">
                <span className="dot-label">{word.due_label}</span>
                {word.context_count ? <span className="dot-label">{word.context_count} ctx</span> : null}
                <select
                  className={`select status-select st-${word.status}`}
                  value={word.status}
                  disabled={busyId === word.id}
                  onChange={(event) => save(word.id, { status: Number(event.target.value) })}
                >
                  {STATUSES.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
                <button type="button" className="btn danger ghost small" onClick={() => removeWord(word)}>
                  Remove
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
