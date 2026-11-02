import { useEffect, useState } from 'react'
import { api } from '../api.js'
import ExplainView from './ExplainView.jsx'

export default function PhrasePanel({ phrase, lessonId, onClose, onSaved }) {
  const [tab, setTab] = useState('translation')
  const [translation, setTranslation] = useState({ loading: true, text: '', error: '' })
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    api
      .translate(phrase.text)
      .then((data) => {
        if (!cancelled)
          setTranslation({ loading: false, text: (data && data.translation) || '', error: '' })
      })
      .catch((err) => {
        if (!cancelled) setTranslation({ loading: false, text: '', error: err.message })
      })
    return () => {
      cancelled = true
    }
  }, [phrase.text])

  async function addToWords() {
    setBusy(true)
    setError('')
    try {
      const data = await api.phrase({
        phrase: phrase.text,
        lesson_id: lessonId,
        sentence: phrase.sentence,
        save: true,
      })
      setSaved(true)
      if (onSaved) onSaved(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <aside className="word-panel surface-phrase">
      <div className="panel-head">
        <div className="panel-head-left">
          <span className="badge">Phrase</span>
          <button
            type="button"
            className="btn ghost small"
            onClick={() => {
              const audio = new Audio(api.ttsUrl(phrase.text))
              audio.play().catch(() => {})
            }}
          >
            Play phrase
          </button>
        </div>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Close phrase panel">
          ×
        </button>
      </div>

      <div className="panel-body">
        <p className="surface" lang="ru">{phrase.text}</p>

        <div className="tabs">
          <button
            type="button"
            className={`tab${tab === 'translation' ? ' active' : ''}`}
            onClick={() => setTab('translation')}
          >
            Translation
          </button>
          <button
            type="button"
            className={`tab${tab === 'explain' ? ' active' : ''}`}
            onClick={() => setTab('explain')}
          >
            Explain
          </button>
        </div>

        {tab === 'translation' ? (
          translation.loading ? (
            <p className="hint">Translating…</p>
          ) : translation.error ? (
            <p className="hint">{translation.error}</p>
          ) : (
            <p className="explain-translation">{translation.text || 'No translation found'}</p>
          )
        ) : (
          <ExplainView
            key={phrase.text}
            word={phrase.text}
            sentence={phrase.sentence}
            translation={translation.text}
          />
        )}

        {error ? <p className="hint">{error}</p> : null}
      </div>

      <div className="panel-foot">
        <span className="dot-label">{phrase.sentence ? 'In sentence' : 'Selection'}</span>
        <button
          type="button"
          className="btn primary small"
          disabled={busy || saved}
          onClick={addToWords}
        >
          {saved ? 'Added' : 'Add to words'}
        </button>
      </div>
    </aside>
  )
}
