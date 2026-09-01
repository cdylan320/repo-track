import { NavLink, Outlet } from 'react-router-dom'
import { IconActivity, IconBoard, IconGear, IconRelays, Mark } from '../icons'
import { countdown } from '../format'
import { useStore } from '../store'

const links = [
  { to: '/', label: 'Overview', icon: <IconBoard />, end: true },
  { to: '/accounts', label: 'Accounts', icon: <IconRelays />, end: false },
  { to: '/activity', label: 'Activity', icon: <IconActivity />, end: false },
  { to: '/settings', label: 'Settings', icon: <IconGear />, end: false },
]

export function Shell() {
  const { overview, toasts, now } = useStore()
  const live = overview?.worker_running
  const faults = overview?.error_count ?? 0

  return (
    <div className="app">
      <aside className="rail">
        <div className="brand">
          <Mark />
          <span className="wordmark">Relay</span>
        </div>
        <nav className="nav">
          {links.map((link) => (
            <NavLink key={link.to} to={link.to} end={link.end} className={({ isActive }) => (isActive ? 'active' : '')}>
              {link.icon}
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="rail-foot">
          <div className="pulse-row">
            <span className={`dot ${faults ? 'fault' : live ? 'live' : 'paused'}`} />
            {faults ? `${faults} fault${faults === 1 ? '' : 's'}` : live ? 'worker live' : 'worker off'}
          </div>
          <div className="pulse-row">
            poll {overview ? `${overview.poll_interval_seconds}s` : '—'}
          </div>
          <div className="pulse-row">
            {overview?.github_paused_until
              ? `GitHub pause ${countdown(overview.github_paused_until, now)}`
              : `next ${countdown(overview?.next_tick_at, now)}`}
          </div>
          {overview?.github_remaining != null ? (
            <div className={`pulse-row${overview.github_remaining < 200 ? ' warn' : ''}`}>
              GitHub API {overview.github_remaining} left
              {overview.poll_auth === 'multi'
                ? ` · ${overview.github_buckets?.length || 1} token${(overview.github_buckets?.length || 1) === 1 ? '' : 's'}`
                : overview.poll_auth === 'dest'
                  ? ' · dest token'
                  : overview.poll_auth === 'origin'
                    ? ' · origin token'
                    : ' · unauthenticated'}
            </div>
          ) : null}
          {(overview?.rate_limited_count ?? 0) > 0 ? (
            <div className="pulse-row warn">
              {overview?.rate_limited_count} origin{(overview?.rate_limited_count ?? 0) === 1 ? '' : 's'} rate-limited
            </div>
          ) : null}
        </div>
      </aside>
      <div className="canvas">
        <nav className="mobile-nav">
          {links.map((link) => (
            <NavLink key={link.to} to={link.to} end={link.end} className={({ isActive }) => (isActive ? 'active' : '')}>
              {link.label}
            </NavLink>
          ))}
        </nav>
        <Outlet />
      </div>
      <div className="toasts">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.bad ? 'bad' : ''}`}>
            {t.text}
          </div>
        ))}
      </div>
    </div>
  )
}
