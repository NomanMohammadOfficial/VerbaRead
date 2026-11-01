import { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function ExplainView({ word, sentence, translation }) {
  const [state, setState] = useState({ loading: true, data: null, error: '' })

  useEffect(() => {
    let cancelled = false
    api
      .explain({ word, sentence, translation })
      .then((data) => {
        if (!cancelled) setState({ loading: false, data, error: '' })
      })
      .catch((err) => {
        if (!cancelled) setState({ loading: false, data: null, error: err.message })
      })
    return () => {
      cancelled = true
    }
  }, [word, sentence, translation])

  if (state.loading) return <p className="hint">Explaining “{word}”…</p>
  if (state.error) return <p className="hint">{state.error}</p>

  const data = state.data || {}
  const points = data.points || []

  return (
    <div className="explain-view">
      {data.summary ? <p className="explain-summary">{data.summary}</p> : null}

      <p className="meta-line">
        {data.lemma ? <strong lang="ru">{data.lemma}</strong> : null}
        {data.pos ? <span> · {data.pos}</span> : null}
        {data.grammar ? <span> · {data.grammar}</span> : null}
      </p>

      {data.translation ? <p className="explain-translation">{data.translation}</p> : null}

      {points.length > 0 ? (
        <ul className="explain-points">
          {points.map((point, index) => (
            <li key={index}>{point}</li>
          ))}
        </ul>
      ) : null}

      {data.source === 'local' ? (
        <p className="hint">Built from local morphology and machine translation.</p>
      ) : null}
    </div>
  )
}
