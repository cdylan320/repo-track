import type { Account } from '../types'
import { relativeTime } from '../format'
import { useStore } from '../store'

export function statusOf(account: Account): { label: string; cls: string } {
  if (account.paused) return { label: 'paused', cls: 'paused' }
  if (account.status === 'syncing') return { label: 'syncing', cls: 'sync' }
  if (account.status === 'error') return { label: 'fault', cls: 'fault' }
  if (account.last_sync_at) return { label: 'live', cls: 'live' }
  return { label: 'armed', cls: 'warn' }
}

export function AccountBlock({ login, caption }: { login: string; caption: string }) {
  return (
    <div className="repo">
      <span className="owner">{caption}</span>
      <span className="name">{login || '—'}</span>
    </div>
  )
}

export function Conduit({ account }: { account: Account }) {
  const st = statusOf(account)
  return (
    <div className="conduit">
      <AccountBlock login={account.origin_account} caption="origin account" />
      <div className={`shaft ${st.cls}`}>
        <span className="bead" />
      </div>
      <AccountBlock login={account.dest_account} caption="dest account" />
    </div>
  )
}

export function StatusTag({ account }: { account: Account }) {
  const st = statusOf(account)
  return (
    <span className="status-tag">
      <span className={`dot ${st.cls}`} />
      {st.label}
    </span>
  )
}

export function PairTime({ account }: { account: Account }) {
  const { now } = useStore()
  return <span>{relativeTime(account.last_sync_at, now)}</span>
}
