import { useEffect, useState, type FormEvent } from 'react'
import type { Account, AccountDraft } from '../types'
import { parseAccount } from '../format'
import { useStore } from '../store'

const blank: AccountDraft = {
  origin_account: '',
  name: '',
  sync_mode: 'ff-only',
  include_forks: false,
}

export function RelayDrawer({
  open,
  initial,
  onClose,
  onSubmit,
}: {
  open: boolean
  initial?: Account | null
  onClose: () => void
  onSubmit: (draft: AccountDraft) => Promise<void>
}) {
  const { overview } = useStore()
  const [draft, setDraft] = useState<AccountDraft>(blank)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const dest = overview?.dest_account || ''

  useEffect(() => {
    if (!open) return
    setError('')
    if (initial) {
      setDraft({
        origin_account: initial.origin_account,
        name: initial.name,
        sync_mode: initial.sync_mode,
        include_forks: initial.include_forks,
      })
    } else {
      setDraft(blank)
    }
  }, [open, initial])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  const originHint = parseAccount(draft.origin_account)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const login = parseAccount(draft.origin_account)
    if (!login) {
      setError('Enter a GitHub user or org.')
      return
    }
    if (!dest) {
      setError('DEST_GITHUB_ACCOUNT is missing from .env')
      return
    }
    setBusy(true)
    setError('')
    try {
      await onSubmit({ ...draft, origin_account: login })
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save')
    } finally {
      setBusy(false)
    }
  }

  function set<K extends keyof AccountDraft>(key: K, value: AccountDraft[K]) {
    setDraft((cur) => ({ ...cur, [key]: value }))
  }

  return (
    <>
      <div className="drawer-back" onClick={onClose} />
      <aside className="drawer">
        <div className="drawer-h">
          <h2>{initial ? 'Edit account' : 'Track an account'}</h2>
          <p>Watch the origin account. Dest only gets brand-new repos and new commits — not a copy of everything already there.</p>
        </div>
        <form className="drawer-b" onSubmit={submit}>
          <div className="field">
            <label htmlFor="origin">Origin account</label>
            <input
              id="origin"
              autoFocus
              placeholder="octocat  or  https://github.com/octocat"
              value={draft.origin_account}
              onChange={(e) => set('origin_account', e.target.value)}
            />
            <span className={`hint ${originHint ? '' : 'muted'}`}>
              {originHint ? `Tracks all repos under ${originHint}` : 'GitHub user or organization.'}
            </span>
          </div>
          <div className="field">
            <label>Destination</label>
            <div className="dest-lock">
              <span className="mono">{dest ? `${dest} / <same repo name>` : 'not set'}</span>
              <span className="hint muted" style={{ marginTop: 6, display: 'block' }}>
                From DEST_GITHUB_ACCOUNT in .env. You never type this here.
              </span>
            </div>
          </div>
          <div className="field">
            <label htmlFor="name">Label</label>
            <input
              id="name"
              placeholder="Optional"
              value={draft.name}
              onChange={(e) => set('name', e.target.value)}
            />
          </div>
          <div className="field">
            <label>Push mode</label>
            <div className="mode">
              <button type="button" className={draft.sync_mode === 'ff-only' ? 'on' : ''} onClick={() => set('sync_mode', 'ff-only')}>
                <strong>Fast-forward</strong>
                <span>Refuse if a dest repo has diverged.</span>
              </button>
              <button type="button" className={draft.sync_mode === 'force' ? 'on' : ''} onClick={() => set('sync_mode', 'force')}>
                <strong>Force</strong>
                <span>Overwrite dest branches.</span>
              </button>
            </div>
          </div>
          <label className="check">
            <input
              type="checkbox"
              checked={draft.include_forks}
              onChange={(e) => set('include_forks', e.target.checked)}
            />
            Include forks
          </label>
          {error ? <div className="err">{error}</div> : null}
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <button className="btn btn-signal" type="submit" disabled={busy || !dest}>
              {busy ? 'Saving…' : initial ? 'Save' : 'Start tracking'}
            </button>
            <button className="btn btn-ghost" type="button" onClick={onClose}>
              Cancel
            </button>
          </div>
        </form>
      </aside>
    </>
  )
}
