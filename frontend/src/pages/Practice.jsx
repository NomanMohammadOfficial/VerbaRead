import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { statusMeta } from '../statuses.js'

const GRADES = [
  { value: 1, label: 'Again', kind: 'again' },
  { value: 2, label: 'Hard', kind: 'hard' },
  { value: 3, label: 'Good', kind: 'good' },
  { value: 4, label: 'Easy', kind: 'easy' },
]

function highlight(sentence, needle) {
  if (!sentence || !needle) return sentence
  const at = sentence.toLowerCase().indexOf(needle.toLowerCase())
  if (at < 0) return sentence
  return [
    sentence.slice(0, at),
    <mark key="mark">{sentence.slice(at, at + needle.length)}</mark>,
    sentence.slice(at + needle.length),
  ]
}

export default function Practice({ onChanged, notify }) {
  const [queue, setQueue] = useState([])
  const [index, setIndex] = useState(0)
  const [revealed, setRevealed] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [sessionCount, setSessionCount] = useState(0)
  const [done, setDone] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    setDone(false)
    setIndex(0)
    setRevealed(false)
    try {
      const data = await api.practiceDue(20)
      setQueue(data.words || [])
    } catch (err) {
      setError(err.message)
      setQueue([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function grade(value) {
    const card = queue[index]
    if (!card || busy) return
    setBusy(true)
    try {
      const result = await api.grade(card.id, value)
      setSessionCount((count) => count + 1)
      notify(`Next review ${result.next_due}`)
      onChanged?.()
      if (index + 1 >= queue.length) {
        setDone(true)
      } else {
        setIndex(index + 1)
        setRevealed(false)
      }
    } catch (err) {
      notify(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const card = queue[index]
  const meta = card ? statusMeta(card.status) : null

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1 className="page-title">Practice</h1>
          <p className="page-sub">
            {queue.length > 0 && !done ? `${index + 1} of ${queue.length}` : `${sessionCount} reviewed`}
          </p>
        </div>
        <div className="head-actions">
          <button type="button" className="btn ghost small" onClick={load} disabled={loading}>
            Reload queue
          </button>
        </div>
      </header>

      {loading ? <div className="state-card">Loading reviews…</div> : null}
      {!loading && error ? <div className="state-card hint error">{error}</div> : null}

      {!loading && !error && done ? (
        <div className="state-card">
          <p>Session complete.</p>
          <p className="dot-label">{sessionCount} cards reviewed</p>
          <button type="button" className="btn primary" onClick={load}>
            Start again
          </button>
        </div>
      ) : null}

      {!loading && !error && !done && queue.length === 0 ? (
        <div className="state-card">
          <p>Nothing due right now.</p>
          <p className="dot-label">Open a lesson and tap a few words to start learning.</p>
          <button type="button" className="btn ghost" onClick={load}>
            Check again
          </button>
        </div>
      ) : null}

      {!loading && !error && !done && card ? (
        <div className="practice-stage">
          <div className="card flashcard">
            <div className="flash-head">
              <span className="dot" style={{ background: meta.color }} />
              <span className="badge">{meta.label}</span>
            </div>
            <p className="flash-lemma">{card.lemma}</p>
            {card.surface && card.surface !== card.lemma ? <p className="dot-label">seen as {card.surface}</p> : null}

            {revealed ? (
              <>
                <p className="flash-translation">{card.translation || 'No translation yet'}</p>
                {card.grammar ? <p className="dot-label">{card.grammar}</p> : null}
                {card.context ? (
                  <blockquote className="flash-context">{highlight(card.context, card.surface || card.lemma)}</blockquote>
                ) : null}
                <div className="grade-row">
                  {GRADES.map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      className={`grade-btn ${item.kind}`}
                      disabled={busy}
                      onClick={() => grade(item.value)}
                    >
                      <strong>{item.label}</strong>
                      {card.options?.[String(item.value)] ? <span>{card.options[String(item.value)]}</span> : null}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <button type="button" className="btn primary" onClick={() => setRevealed(true)}>
                Show answer
              </button>
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}
