import { api } from '../api.js'
import { STATUSES } from '../statuses.js'

export default function Stats({ stats, refreshStats }) {
  if (!stats) {
    return (
      <div className="page">
        <div className="state-card">Loading…</div>
      </div>
    )
  }

  const byStatus = stats.byStatus || {}
  const total = STATUSES.reduce((sum, item) => sum + (byStatus[String(item.value)] || 0), 0)
  const scale = Math.max(1, total)
  const days = Array.isArray(stats.reviewsByDay) ? stats.reviewsByDay : []
  const maxReviews = Math.max(1, ...days.map((item) => item.count || 0))

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1 className="page-title">Progress</h1>
          <p className="page-sub">How much Russian you have collected so far.</p>
        </div>
        <div className="head-actions">
          <a className="btn ghost" href={api.ankiUrl}>
            Export Anki
          </a>
          <button type="button" className="btn" onClick={refreshStats}>
            Refresh
          </button>
        </div>
      </header>

      <div className="stat-grid">
        <div className="card stat-card">
          <span className="stat-label">Words saved</span>
          <span className="stat-value">{stats.totalWords}</span>
        </div>
        <div className="card stat-card">
          <span className="stat-label">Due now</span>
          <span className="stat-value">{stats.due}</span>
        </div>
        <div className="card stat-card">
          <span className="stat-label">Lessons</span>
          <span className="stat-value">{stats.lessons}</span>
        </div>
        <div className="card stat-card">
          <span className="stat-label">Reviewed today</span>
          <span className="stat-value">{stats.reviewedToday}</span>
        </div>
        <div className="card stat-card">
          <span className="stat-label">Study streak</span>
          <span className="stat-value">{stats.streakDays}d</span>
        </div>
      </div>

      <section className="card">
        <h2 className="section-title">Word status</h2>
        <div className="distribution">
          {STATUSES.map((item) => (
            <span
              key={item.value}
              className="distribution-seg"
              style={{ width: `${((byStatus[String(item.value)] || 0) / scale) * 100}%`, background: item.color }}
              title={`${item.label}: ${byStatus[String(item.value)] || 0}`}
            />
          ))}
        </div>
        <div className="legend">
          {STATUSES.map((item) => (
            <span key={item.value} className="legend-item">
              <span className="dot" style={{ background: item.color }} />
              {item.label} · {byStatus[String(item.value)] || 0}
            </span>
          ))}
        </div>
      </section>

      <section className="card">
        <h2 className="section-title">Reviews this week</h2>
        <div className="bars">
          {days.map((item) => (
            <div key={item.day} className="bar-col">
              <span className="bar" style={{ height: `${((item.count || 0) / maxReviews) * 100}%` }} />
              <span className="bar-label">
                {new Date(item.day * 1000).toLocaleDateString(undefined, { weekday: 'short' })}
              </span>
            </div>
          ))}
        </div>
        {days.length === 0 ? <p className="hint">No reviews yet. Practice a few words to start the chart.</p> : null}
      </section>
    </div>
  )
}
