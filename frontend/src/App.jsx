import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import Library from './pages/Library.jsx'
import Reader from './pages/Reader.jsx'
import Vocabulary from './pages/Vocabulary.jsx'
import Practice from './pages/Practice.jsx'
import Stats from './pages/Stats.jsx'

const ICONS = {
  library: [
    'M4 5.5A1.5 1.5 0 0 1 5.5 4H10v16H5.5A1.5 1.5 0 0 1 4 18.5z',
    'M10 4h8.5A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5H10z',
  ],
  words: [
    'M4 6.5A2.5 2.5 0 0 1 6.5 4H20v14.5A1.5 1.5 0 0 1 18.5 20H6.5A2.5 2.5 0 0 1 4 17.5z',
    'M8 8h8',
    'M8 12h6',
  ],
  practice: [
    'M4 7h11a3 3 0 0 1 0 6H9l-3 4',
    'M4 13h9',
    'M17 15l3 3',
  ],
  stats: [
    'M4 20V10',
    'M10 20V4',
    'M16 20v-7',
    'M22 20H2',
  ],
  spark: [
    'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z',
  ],
}

const NAV = [
  { id: 'library', label: 'Library', icon: 'library' },
  { id: 'words', label: 'Vocabulary', icon: 'words' },
  { id: 'practice', label: 'Practice', icon: 'practice' },
  { id: 'stats', label: 'Stats', icon: 'stats' },
]

function Icon({ name }) {
  const paths = ICONS[name] || ICONS.spark
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths.map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  )
}

function getRouteFromLocation() {
  const hash = window.location.hash
  if (hash) {
    const matchHash = hash.match(/^#\/?(?:reader|lesson)\/(\d+)$/)
    if (matchHash) {
      return { page: 'reader', lessonId: parseInt(matchHash[1], 10) }
    }
    const cleanHash = hash.replace(/^#\/?/, '')
    if (['words', 'practice', 'stats', 'library'].includes(cleanHash)) {
      return { page: cleanHash, lessonId: null }
    }
  }

  const params = new URLSearchParams(window.location.search)
  const queryLesson = params.get('lesson') || params.get('reader')
  if (queryLesson && /^\d+$/.test(queryLesson)) {
    return { page: 'reader', lessonId: parseInt(queryLesson, 10) }
  }

  const path = window.location.pathname.replace(/\/+$/, '') || '/'
  const matchReader = path.match(/^\/(?:reader|lesson)\/(\d+)$/)
  if (matchReader) {
    return { page: 'reader', lessonId: parseInt(matchReader[1], 10) }
  }
  if (path === '/words') return { page: 'words', lessonId: null }
  if (path === '/practice') return { page: 'practice', lessonId: null }
  if (path === '/stats') return { page: 'stats', lessonId: null }
  return { page: 'library', lessonId: null }
}

function updateBrowserUrl(toPage, toLessonId = null) {
  let targetUrl = '/'
  if (toPage === 'reader' && toLessonId) {
    targetUrl = `/reader/${toLessonId}`
  } else if (toPage && toPage !== 'library') {
    targetUrl = `/${toPage}`
  }

  if (window.location.pathname !== targetUrl) {
    window.history.pushState({ page: toPage, lessonId: toLessonId }, '', targetUrl)
  }
}

export default function App() {
  const initialRoute = getRouteFromLocation()
  const [page, setPage] = useState(initialRoute.page)
  const [lessonId, setLessonId] = useState(initialRoute.lessonId)
  const [stats, setStats] = useState(null)
  const [toast, setToast] = useState(null)
  const timerRef = useRef(null)

  useEffect(() => {
    const onPopState = () => {
      const route = getRouteFromLocation()
      setPage(route.page)
      setLessonId(route.lessonId)
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const refreshStats = useCallback(() => {
    api.stats().then(setStats).catch(() => setStats(null))
  }, [])

  useEffect(() => {
    refreshStats()
  }, [refreshStats])

  useEffect(() => () => clearTimeout(timerRef.current), [])

  function notify(text, kind = 'ok') {
    clearTimeout(timerRef.current)
    setToast({ id: Date.now(), text, kind })
    timerRef.current = setTimeout(() => setToast(null), 3200)
  }

  function openLesson(id) {
    setLessonId(id)
    setPage('reader')
    updateBrowserUrl('reader', id)
  }

  function go(next) {
    setPage(next)
    setLessonId(null)
    updateBrowserUrl(next)
  }

  const activePage = page === 'reader' && !lessonId ? 'library' : page
  const due = stats?.due || 0

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">РУ</span>
          <span>
            <strong>Russian reader</strong>
            <small>Read · tap · remember</small>
          </span>
        </div>
        <nav className="nav">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`nav-item${activePage === item.id ? ' active' : ''}`}
              onClick={() => go(item.id)}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
              {item.id === 'practice' && due > 0 ? <span className="nav-badge">{due}</span> : null}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <a className="btn ghost small" href={api.ankiUrl} download="ru-reader-anki.txt">
            Export to Anki
          </a>
          <small>Local · SQLite</small>
        </div>
      </aside>

      <main className="main">
        {page === 'reader' && lessonId ? (
          <Reader
            key={lessonId}
            lessonId={lessonId}
            onBack={() => {
              go('library')
              refreshStats()
            }}
            onChanged={refreshStats}
            notify={notify}
          />
        ) : null}
        {page === 'library' ? <Library onOpenLesson={openLesson} notify={notify} /> : null}
        {page === 'words' ? <Vocabulary onChanged={refreshStats} notify={notify} /> : null}
        {page === 'practice' ? <Practice onChanged={refreshStats} notify={notify} /> : null}
        {page === 'stats' ? <Stats stats={stats} refreshStats={refreshStats} /> : null}
      </main>

      {toast ? (
        <div key={toast.id} className={`toast ${toast.kind}`} role="status">
          {toast.text}
        </div>
      ) : null}
    </div>
  )
}
