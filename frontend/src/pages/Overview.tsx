import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { CommitFeed } from '../components/CommitFeed'
import { RelayDrawer } from '../components/RelayDrawer'
import { StatusTag } from '../components/PairVisual'
import { Schema } from '../icons'
import { relativeTime, todayLabel } from '../format'
import { useStore } from '../store'
import type { AccountDraft } from '../types'

export function OverviewPage() {
  const { overview, accounts, activity, loading, now, refresh, toast } = useStore()
  const [open, setOpen] = useState(false)
  const [syncing, setSyncing] = useState(false)

  async function create(draft: AccountDraft) {
    await api.createAccount(draft)
    await refresh()
    toast('Account tracking started')
  }

  async function syncAll() {
    setSyncing(true)
    try {
      await api.syncAll()
      await refresh()
      toast('All accounts synced')
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Sync failed', true)
    } finally {
      setSyncing(false)
    }
  }

  if (loading) {
    return (
      <>
        <div className="topbar">
          <span className="crumb">{todayLabel()}</span>
        </div>
        <div className="page">
          <p className="muted">Loading the board…</p>
        </div>
      </>
    )
  }

  if (accounts.length === 0) {
    return (
      <>
        <div className="topbar">
          <span className="crumb">Overview</span>
        </div>
        <div className="hero-empty">
          <div className="hero-copy">
            <Schema />
            <h1>Nothing is moving yet.</h1>
            <p>
              Track a GitHub account. Dest stays empty until origin creates a <strong>new repo</strong> or
              anyone pushes a <strong>new commit</strong> — existing idle repos are not copied.
            </p>
            {!overview?.discord_configured ? (
              <p className="muted" style={{ marginTop: -12 }}>
                Discord is off until DISCORD_WEBHOOK_URL is set in .env.
              </p>
            ) : null}
            {!overview?.dest_account ? (
              <p className="muted">Set DEST_GITHUB_ACCOUNT in .env before you start.</p>
            ) : null}
            <button className="btn btn-signal" type="button" onClick={() => setOpen(true)}>
              Track an account
            </button>
          </div>
        </div>
        <RelayDrawer open={open} onClose={() => setOpen(false)} onSubmit={create} />
      </>
    )
  }

  const headline =
    (overview?.error_count ?? 0) > 0
      ? 'Something needs attention.'
      : accounts.some((p) => p.status === 'syncing')
        ? 'Relaying now.'
        : 'The board is live.'

  return (
    <>
      <div className="topbar">
        <span className="crumb">{todayLabel()}</span>
        <div className="top-actions">
          <button className="btn" type="button" onClick={syncAll} disabled={syncing}>
            {syncing ? 'Syncing…' : 'Sync all'}
          </button>
          <button className="btn btn-signal" type="button" onClick={() => setOpen(true)}>
            Track account
          </button>
        </div>
      </div>
      <div className="page">
        <div className="page-head">
          <div>
            <h1 className="display">{headline}</h1>
            <p className="lede">
              {overview?.active_count ?? 0} accounts
              {(overview?.repo_count ?? 0) ? ` · ${overview?.repo_count} repos` : ''}
              {(overview?.error_count ?? 0) ? ` · ${overview?.error_count} faulting` : ''}
              {overview?.dest_account ? ` · dest ${overview.dest_account}` : ''}
            </p>
          </div>
        </div>
        <div className="strip">
          <div className="strip-cell">
            <div className="strip-k">Relayed today</div>
            <div className="strip-v">{overview?.commits_today ?? 0}</div>
            <div className="strip-s">{overview?.commits_total ?? 0} all-time</div>
          </div>
          <div className="strip-cell">
            <div className="strip-k">Repos</div>
            <div className="strip-v small">{overview?.repo_count ?? 0}</div>
            <div className="strip-s">{overview?.account_count ?? 0} accounts</div>
          </div>
          <div className="strip-cell">
            <div className="strip-k">Last pulse</div>
            <div className="strip-v small">{relativeTime(overview?.last_sync_at, now)}</div>
            <div className="strip-s">poll {overview?.poll_interval_seconds ?? '—'}s</div>
          </div>
          <div className="strip-cell">
            <div className="strip-k">Discord</div>
            <div className="strip-v small">{overview?.discord_configured ? 'on' : 'off'}</div>
            <div className="strip-s">{overview?.dest_token_configured ? 'dest token on' : 'no dest token'}</div>
          </div>
        </div>
        <div className="board">
          <section className="panel">
            <div className="panel-h">
              Accounts
              <Link to="/accounts">View all</Link>
            </div>
            {accounts.map((account) => (
              <Link key={account.id} to={`/accounts/${account.id}`} className="pair-row">
                <StatusTag account={account} />
                <div>
                  <div>
                    {account.origin_account} → {account.dest_account}
                  </div>
                  <div className="pair-meta">
                    {account.repo_count} repos · {account.commits_synced} relayed
                  </div>
                </div>
                <span className="muted mono" style={{ fontSize: 12 }}>
                  {relativeTime(account.last_sync_at, now)}
                </span>
              </Link>
            ))}
          </section>
          <section className="panel">
            <div className="panel-h">
              Latest activity
              <Link to="/activity">Activity</Link>
            </div>
            <CommitFeed items={activity.slice(0, 12)} toPair />
          </section>
        </div>
      </div>
      <RelayDrawer open={open} onClose={() => setOpen(false)} onSubmit={create} />
    </>
  )
}
