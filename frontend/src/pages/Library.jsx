import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'

function timeAgo(seconds) {
  if (!seconds) return 'never opened'
  const diff = Math.floor(Date.now() / 1000) - Number(seconds)
  if (diff < 90) return 'just now'
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  if (diff < 86400 * 30) return `${Math.round(diff / 86400)}d ago`
  return new Date(Number(seconds) * 1000).toLocaleDateString()
}

export default function Library({ onOpenLesson, notify }) {
  const [lessons, setLessons] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('text')
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [url, setUrl] = useState('')
  const [audioUrl, setAudioUrl] = useState('')
  const [preview, setPreview] = useState(null)
  const [fetching, setFetching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [manualText, setManualText] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      const data = await api.lessons()
      setLessons(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function fetchTranscript() {
    if (!url.trim()) {
      notify('Paste a YouTube link first', 'error')
      return
    }
    setFetching(true)
    try {
      const result = await api.youtube(url.trim())
      setPreview(result)
      if (!title.trim()) setTitle(`YouTube ${result.videoId}`)
      if (result.cues?.length) {
        notify(`${result.cues.length} cues (${result.language || 'auto'})`)
      } else {
        notify(result.error || 'No transcript found. Paste the text below.', 'error')
      }
    } catch (err) {
      setPreview(null)
      notify(err.message, 'error')
    } finally {
      setFetching(false)
    }
  }

  async function importLesson(event) {
    event.preventDefault()
    if (!title.trim()) {
      notify('Give this lesson a title', 'error')
      return
    }
    const body = { title: title.trim() }
    if (tab === 'youtube') {
      if (!url.trim()) {
        notify('Paste a YouTube link', 'error')
        return
      }
      body.source_type = 'youtube'
      body.youtube_url = url.trim()
      if (audioUrl.trim()) body.audio_url = audioUrl.trim()
      if (manualText.trim()) {
        body.text = manualText.trim()
        body.cues = []
      } else if (preview && !preview.cues?.length) {
        notify('Paste the transcript text for this video', 'error')
        return
      } else if (preview?.cues?.length) {
        body.cues = preview.cues
      }
    } else {
      if (text.trim().length < 20) {
        notify('Paste at least a couple of sentences', 'error')
        return
      }
      body.text = text.trim()
      if (audioUrl.trim()) body.audio_url = audioUrl.trim()
    }

    setSaving(true)
    try {
      const lesson = await api.createLesson(body)
      setTitle('')
      setText('')
      setUrl('')
      setAudioUrl('')
      setPreview(null)
      setManualText('')
      await load()
      notify('Lesson added')
      onOpenLesson(lesson.id)
    } catch (err) {
      notify(err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  async function removeLesson(id) {
    if (!window.confirm('Delete this lesson? Word history stays.')) return
    try {
      await api.deleteLesson(id)
      await load()
      notify('Lesson deleted')
    } catch (err) {
      notify(err.message, 'error')
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1 className="page-title">Library</h1>
          <p className="page-sub">{lessons.length} lessons · tap a word to save it</p>
        </div>
        <div className="head-actions">
          <button type="button" className="btn ghost small" onClick={load}>
            Refresh
          </button>
        </div>
      </header>

      <form className="card import-card" onSubmit={importLesson}>
        <div className="tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'text'}
            className={`tab${tab === 'text' ? ' active' : ''}`}
            onClick={() => setTab('text')}
          >
            Paste text
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'youtube'}
            className={`tab${tab === 'youtube' ? ' active' : ''}`}
            onClick={() => setTab('youtube')}
          >
            YouTube
          </button>
        </div>

        <label className="field">
          <span className="field-label">Title</span>
          <input
            className="input"
            value={title}
            placeholder="В гостях у бабушки"
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>

        {tab === 'text' ? (
          <label className="field">
            <span className="field-label">Russian text</span>
            <textarea
              className="textarea"
              rows={7}
              value={text}
              placeholder="В субботу я поехал к бабушке..."
              onChange={(event) => setText(event.target.value)}
            />
            <span className="hint-inline">{text.trim().length} characters</span>
          </label>
        ) : (
          <>
            <label className="field">
              <span className="field-label">YouTube link</span>
              <div className="inline-field">
                <input
                  className="input"
                  value={url}
                  placeholder="https://www.youtube.com/watch?v=..."
                  onChange={(event) => {
                    setUrl(event.target.value)
                    setPreview(null)
                    setManualText('')
                  }}
                />
                <button type="button" className="btn ghost small" onClick={fetchTranscript} disabled={fetching}>
                  {fetching ? 'Fetching…' : 'Fetch transcript'}
                </button>
              </div>
              {preview ? (
                <span className={`hint-inline${preview.cues?.length ? '' : ' error'}`}>
                  {preview.cues?.length
                    ? `${preview.cues.length} cues · ${preview.language || 'auto'}`
                    : preview.error || 'No transcript found. Paste the text below.'}
                </span>
              ) : null}
            </label>

            {preview && !preview.cues?.length ? (
              <details className="field" open>
                <summary>Paste the transcript text</summary>
                <textarea
                  className="textarea"
                  rows={6}
                  value={manualText}
                  placeholder="Paste the Russian transcript here..."
                  onChange={(event) => setManualText(event.target.value)}
                />
              </details>
            ) : null}
          </>
        )}

        <label className="field">
          <span className="field-label">Audio URL (optional)</span>
          <input
            className="input"
            value={audioUrl}
            placeholder="https://.../audio.mp3"
            onChange={(event) => setAudioUrl(event.target.value)}
          />
        </label>

        <div className="head-actions">
          <button type="submit" className="btn primary" disabled={saving}>
            {saving ? 'Adding…' : 'Add lesson'}
          </button>
        </div>
      </form>

      {loading ? <div className="state-card">Loading lessons…</div> : null}
      {!loading && error ? <div className="state-card hint error">{error}</div> : null}

      {!loading && !error && lessons.length === 0 ? (
        <div className="state-card">No lessons yet. Paste Russian text or a YouTube link above.</div>
      ) : null}

      <div className="lesson-list">
        {lessons.map((lesson) => {
          const pct = Math.round((lesson.knownWords / Math.max(1, lesson.uniqueWords)) * 100)
          return (
            <article key={lesson.id} className="card lesson-card">
              <div className="lesson-top">
                <h3>
                  <button type="button" className="lesson-title" onClick={() => onOpenLesson(lesson.id)}>
                    {lesson.title}
                  </button>
                </h3>
                <div className="lesson-actions">
                  <span className={`badge${lesson.source_type === 'youtube' ? ' video' : ''}`}>
                    {lesson.source_type === 'youtube' ? 'video' : 'text'}
                  </span>
                  <button type="button" className="btn ghost small" onClick={() => onOpenLesson(lesson.id)}>
                    Read
                  </button>
                  <button type="button" className="btn danger ghost small" onClick={() => removeLesson(lesson.id)}>
                    Delete
                  </button>
                </div>
              </div>
              <p className="meta-line">
                <span>{lesson.uniqueWords} words</span>
                <span> · {timeAgo(lesson.last_opened_at)}</span>
              </p>
              <p className="lesson-excerpt">{lesson.excerpt}…</p>
              <div className="lesson-progress">
                <div className="lesson-progress-bar" style={{ width: `${pct}%` }} />
              </div>
              <div className="lesson-counts">
                <span className="dot-label">
                  {lesson.knownWords}/{lesson.uniqueWords} known
                </span>
                {lesson.newWords > 0 ? <span className="chip st-1">{lesson.newWords} new</span> : null}
                {lesson.learningWords > 0 ? <span className="chip st-2">{lesson.learningWords} learning</span> : null}
                {lesson.knownWords > 0 ? <span className="chip st-3">{lesson.knownWords} known</span> : null}
              </div>
            </article>
          )
        })}
      </div>
    </div>
  )
}
