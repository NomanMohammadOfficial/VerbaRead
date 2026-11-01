import { useEffect, useState } from 'react'
import { api } from '../api.js'

const GENDERS = { m: 'masculine', f: 'feminine', n: 'neuter' }
const CASES = ['nom', 'gen', 'dat', 'acc', 'inst', 'prep']

function summary(data) {
  const parts = []
  if (data.type) parts.push(data.type)
  if (GENDERS[data.gender]) parts.push(GENDERS[data.gender])
  if (data.type === 'noun') parts.push(data.animate ? 'animate' : 'inanimate')
  if (data.rank) parts.push(`#${data.rank}`)
  return parts.join(' · ')
}

function Forms({ forms }) {
  const rows = CASES.filter((key) => (forms.sg || {})[key] || (forms.pl || {})[key])
  if (rows.length === 0) return null
  return (
    <div className="dict-section">
      <h4 className="dict-title">Forms</h4>
      <div className="dict-forms">
        {rows.map((key) => (
          <div className="dict-form-row" key={key}>
            <span className="dict-form-label">{key}</span>
            <span className="dict-form" lang="ru">{(forms.sg || {})[key] || '—'}</span>
            <span className="dict-form" lang="ru">{(forms.pl || {})[key] || '—'}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function DictionaryView({ lemma }) {
  const [state, setState] = useState({ loading: true, data: null, error: '' })

  useEffect(() => {
    let cancelled = false
    api
      .dictionary(lemma)
      .then((data) => {
        if (cancelled) return
        if (data && data.found) setState({ loading: false, data, error: '' })
        else
          setState({
            loading: false,
            data: null,
            error: (data && data.error) || 'No dictionary entry for this word',
          })
      })
      .catch((err) => {
        if (!cancelled) setState({ loading: false, data: null, error: err.message })
      })
    return () => {
      cancelled = true
    }
  }, [lemma])

  if (state.loading) return <p className="hint">Looking up “{lemma}”…</p>
  if (state.error) return <p className="hint">{state.error}</p>

  const data = state.data
  const meta = summary(data)

  return (
    <div className="dict-view">
      <div className="dict-head">
        <span className="dict-accented" lang="ru">{data.accented || data.lemma}</span>
        {data.level ? <span className="badge">{data.level}</span> : null}
      </div>
      {meta ? <p className="dict-meta">{meta}</p> : null}
      {data.audio ? <audio className="dict-audio" src={data.audio} controls preload="none" /> : null}
      {data.translations.length > 0 ? (
        <p className="dict-glosses">{data.translations.join(' · ')}</p>
      ) : null}

      {data.meanings.length > 0 ? (
        <div className="dict-section">
          <h4 className="dict-title">Meanings</h4>
          {data.meanings.slice(0, 4).map((item, index) => (
            <div className="dict-meaning" key={`${item.definition}-${index}`}>
              {item.definition ? <p className="dict-definition">{item.definition}</p> : null}
              {item.glosses.length > 0 ? <p className="dict-gloss">{item.glosses.join('; ')}</p> : null}
              {item.example_ru ? (
                <blockquote lang="ru">
                  {item.example_ru}
                  {item.example_tl ? <span className="dict-translation">{item.example_tl}</span> : null}
                </blockquote>
              ) : null}
              {item.rare ? <span className="dict-rare">rare</span> : null}
            </div>
          ))}
        </div>
      ) : null}

      {data.examples.length > 0 ? (
        <div className="dict-section">
          <h4 className="dict-title">Examples</h4>
          <div className="contexts">
            {data.examples.slice(0, 4).map((item, index) => (
              <blockquote key={`${item.ru}-${index}`} lang="ru">
                {item.ru}
                {item.tl ? <span className="dict-translation">{item.tl}</span> : null}
              </blockquote>
            ))}
          </div>
        </div>
      ) : null}

      {data.forms ? <Forms forms={data.forms} /> : null}

      {data.source ? <p className="hint">Source: {data.source}</p> : null}
    </div>
  )
}
