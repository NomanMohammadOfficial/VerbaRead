import { useEffect, useRef, useState } from 'react'
import { STATUSES } from '../statuses.js'
import DictionaryView from './DictionaryView.jsx'
import ExplainView from './ExplainView.jsx'

const TABS = [
  { id: 'translation', label: 'Translation' },
  { id: 'dictionary', label: 'Dictionary' },
  { id: 'explain', label: 'Explain' },
]

export default function WordPanel({ word, busy, onClose, onSave, onRemove, onPlayWord }) {
  const [tab, setTab] = useState('translation')
  const [translation, setTranslation] = useState(word?.translation || '')
  const [grammar, setGrammar] = useState(word?.grammar || '')
  const cancelRef = useRef(false)

  useEffect(() => {
    setTranslation(word?.translation || '')
    setGrammar(word?.grammar || '')
    cancelRef.current = false
  }, [word?.id, word?.translation, word?.grammar])

  if (!word) return null

  function reset() {
    setTranslation(word.translation || '')
    setGrammar(word.grammar || '')
  }

  function cancel() {
    cancelRef.current = true
    reset()
  }

  function commit(field, value) {
    if (cancelRef.current) {
      cancelRef.current = false
      return
    }
    const trimmed = value.trim()
    if (trimmed === (word[field] || '').trim()) return
    if (!trimmed) return
    onSave({ [field]: trimmed })
  }

  const contexts = word.contexts || []
  const surface = word.surface || word.lemma
  const sentence = word.sentence || contexts[0]?.sentence || ''

  return (
    <aside className="word-panel">
      <div className="panel-head">
        <div className="panel-head-left">
          <span className="badge">Word</span>
          {busy ? <span className="panel-busy">Looking up…</span> : null}
        </div>
        <div className="panel-head-left">
          <button type="button" className="btn ghost small" onClick={onPlayWord}>
            Play word
          </button>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close word panel">
            ×
          </button>
        </div>
      </div>

      <div className="panel-body">
        <p className="surface">{surface}</p>
        <p className="meta-line">
          <strong>{word.lemma}</strong>
          {word.pos ? <span> · {word.pos}</span> : null}
          {word.grammar && tab === 'translation' ? <span> · {word.grammar}</span> : null}
        </p>

        <div className="tabs" role="tablist">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              className={`tab${tab === item.id ? ' active' : ''}`}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="field">
          <span className="field-label">Status</span>
          <div className="status-picker">
            {STATUSES.filter((item) => item.value > 0).map((item) => (
              <button
                key={item.value}
                type="button"
                className={`status-dot${Number(word.status) === item.value ? ' active' : ''}`}
                style={{ '--dot': item.color }}
                title={item.label}
                aria-label={item.label}
                disabled={busy}
                onClick={() => onSave({ status: item.value })}
              />
            ))}
            <span className="dot-label">
              {(STATUSES.find((item) => item.value === Number(word.status)) || STATUSES[0]).label}
            </span>
          </div>
        </div>

        {tab === 'translation' ? (
          <>
            <label className="field">
              <span className="field-label">Translation</span>
              <input
                className="input"
                value={translation}
                placeholder={busy ? 'Looking up…' : 'Add a translation'}
                disabled={busy}
                onChange={(event) => setTranslation(event.target.value)}
                onFocus={() => {
                  cancelRef.current = false
                }}
                onBlur={() => commit('translation', translation)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') event.currentTarget.blur()
                  if (event.key === 'Escape') {
                    cancel()
                    event.currentTarget.blur()
                  }
                }}
              />
            </label>

            <label className="field">
              <span className="field-label">Grammar</span>
              <input
                className="input"
                value={grammar}
                placeholder="noun · feminine · dative"
                disabled={busy}
                onChange={(event) => setGrammar(event.target.value)}
                onFocus={() => {
                  cancelRef.current = false
                }}
                onBlur={() => commit('grammar', grammar)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') event.currentTarget.blur()
                  if (event.key === 'Escape') {
                    cancel()
                    event.currentTarget.blur()
                  }
                }}
              />
            </label>

            {contexts.length > 0 ? (
              <div className="contexts">
                <span className="field-label">Seen in</span>
                {contexts.map((item, index) => (
                  <blockquote key={`${item.lesson_id}-${index}`}>{item.sentence}</blockquote>
                ))}
              </div>
            ) : null}
          </>
        ) : null}

        {tab === 'dictionary' ? <DictionaryView key={word.lemma} lemma={word.lemma} /> : null}

        {tab === 'explain' ? (
          <ExplainView
            key={word.id || word.lemma}
            word={surface}
            sentence={sentence}
            translation={word.translation || ''}
          />
        ) : null}
      </div>

      <div className="panel-foot">
        <span className="dot-label">{word.due_label || 'new'}</span>
        <button type="button" className="btn danger ghost small" disabled={busy} onClick={onRemove}>
          Remove
        </button>
      </div>
    </aside>
  )
}
