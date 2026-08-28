import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { CommitFeed } from '../components/CommitFeed'
import { Confirm } from '../components/Confirm'
import { Conduit, StatusTag } from '../components/PairVisual'
import { RelayDrawer } from '../components/RelayDrawer'
import { clockTime, relativeTime } from '../format'
import { useStore } from '../store'
import type { Account, AccountDraft, CommitItem, LogItem, RepoItem } from '../types'

export function RelayDetailPage() {
  const { id } = useParams()
  const accountId = Number(id)
  const nav = useNavigate()
  const { refresh, dropAccount, toast, overview, now } = useStore()
  const [account, setAccount] = useState<Account | null>(null)
  const [commits, setCommits] = useState<CommitItem[]>([])
  const [logs, setLogs] = useState<LogItem[]>([])
  const [edit, setEdit] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const [p, c, l] = await Promise.all([api.account(accountId), api.activity(accountId), api.logs(accountId)])
    setAccount(p)
    setCommits(c)
    setLogs(l)
  }, [accountId])

  useEffect(() => {
    if (!Number.isFinite(accountId)) return
    load().catch((err: Error) => toast(err.message, true))
  }, [accountId, load, toast, overview?.last_sync_at])

  async function sync() {
    setBusy(true)
    try {
      const result = await api.syncAccount(accountId)
      await Promise.all([load(), refresh()])
      toast(result.count ? `Relayed ${result.count} commit${result.count === 1 ? '' : 's'}` : 'Already up to date')
    } catch (err) {
      await load()
      toast(err instanceof Error ? err.message : 'Sync failed', true)
    } finally {
      setBusy(false)
    }
  }

  async function togglePause() {
    if (!account) return
    await api.updateAccount(account.id, { paused: !account.paused })
    await Promise.all([load(), refresh()])
  }

  async function save(draft: AccountDraft) {
    await api.updateAccount(accountId, draft)
    await Promise.all([load(), refresh()])
    toast('Account updated')
  }

  function remove() {
    setConfirm(false)
    dropAccount(accountId)
    nav('/accounts')
    toast('Account removed')
    void api.deleteAccount(accountId).then(() => refresh()).catch((err: Error) => toast(err.message, true))
  }

  if (!account) {
    return (
      <>
        <div className="topbar">
          <span className="crumb">
            <Link to="/accounts">Accounts</Link>
          </span>
        </div>
        <div className="page">
          <p className="muted">Loading…</p>
        </div>
      </>
    )
  }

  const repos: RepoItem[] = account.repos || []

  return (
    <>
      <div className="topbar">
        <span className="crumb">
          <Link to="/accounts">Accounts</Link>
          <span> / {account.origin_account}</span>
        </span>
      </div>
      <div className="page">
        <div className="detail-hero">
          <div>
            <StatusTag account={account} />
            <h1 className="display" style={{ marginTop: 12, fontSize: 36 }}>
              {account.origin_account}
            </h1>
            <p className="lede">
              → {account.dest_account} · {account.repo_count} repos · last pulse {relativeTime(account.last_sync_at, now)}
              {account.last_sync_at ? ` · ${clockTime(account.last_sync_at)}` : ''}
            </p>
          </div>
          <div className="detail-actions">
            <button className="btn btn-signal" type="button" onClick={sync} disabled={busy}>
              {busy || account.status === 'syncing' ? 'Syncing…' : 'Sync now'}
            </button>
            <button className="btn" type="button" onClick={togglePause}>
              {account.paused ? 'Resume' : 'Pause'}
            </button>
            <button className="btn" type="button" onClick={() => setEdit(true)}>
              Edit
            </button>
            <button className="btn btn-danger" type="button" onClick={() => setConfirm(true)}>
              Remove
            </button>
          </div>
        </div>

        <div className="panel" style={{ padding: 20, marginBottom: 20 }}>
          <Conduit account={account} />
        </div>

        {account.last_error ? <div className="err">{account.last_error}</div> : null}

        <div className="split">
          <section className="panel">
            <div className="panel-h">Repos</div>
            {repos.length === 0 ? (
              <div className="empty">
                <p className="muted">No repos discovered yet.</p>
              </div>
            ) : (
              repos.map((repo) => (
                <div key={repo.id} className="repo-line">
                  <div>
                    <div className="mono">
                      {account.origin_account}/{repo.name} → {account.dest_account}/{repo.name}
                    </div>
                    <div className="sub">
                      {repo.mirrored ? 'on dest' : 'watching'}
                      {' · '}
                      {repo.default_branch}
                      {repo.private ? ' · private' : ' · public'} · {repo.commits_synced} relayed
                      {repo.last_sha ? ` · ${repo.last_sha.slice(0, 7)}` : ''}
                      {repo.status === 'error' ? ` · ${repo.last_error}` : ''}
                    </div>
                  </div>
                  <span className={`dot ${repo.status === 'error' ? 'fault' : repo.last_sha ? 'live' : 'warn'}`} />
                </div>
              ))
            )}
            <div className="panel-h" style={{ borderTop: '1px solid var(--line)' }}>
              Commits
            </div>
            <CommitFeed items={commits} />
          </section>
          <section className="panel">
            <div className="panel-h">Log</div>
            {logs.length === 0 ? (
              <div className="empty">
                <p className="muted">No events yet.</p>
              </div>
            ) : (
              logs.map((item) => (
                <div key={item.id} className="log">
                  <div className={`kind ${item.kind}`}>{item.kind}</div>
                  <div style={{ marginTop: 4 }}>{item.message}</div>
                  {item.detail ? (
                    <div className="sub" style={{ whiteSpace: 'pre-wrap' }}>
                      {item.detail}
                    </div>
                  ) : null}
                  <div className="sub">{clockTime(item.created_at)}</div>
                </div>
              ))
            )}
          </section>
        </div>
      </div>
      <RelayDrawer open={edit} initial={account} onClose={() => setEdit(false)} onSubmit={save} />
      <Confirm
        open={confirm}
        title="Stop tracking this account?"
        body="Clones are deleted. Destination GitHub repos are left untouched."
        confirmLabel="Remove"
        onCancel={() => setConfirm(false)}
        onConfirm={remove}
      />
    </>
  )
}
