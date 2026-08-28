import { useState } from 'react'
import { api } from '../api'
import { PairCard } from '../components/PairCard'
import { RelayDrawer } from '../components/RelayDrawer'
import { Schema } from '../icons'
import { useStore } from '../store'
import type { AccountDraft } from '../types'

export function RelaysPage() {
  const { accounts, refresh, toast, overview } = useStore()
  const [open, setOpen] = useState(false)

  async function create(draft: AccountDraft) {
    await api.createAccount(draft)
    await refresh()
    toast('Account tracking started')
  }

  return (
    <>
      <div className="topbar">
        <span className="crumb">Accounts</span>
        <div className="top-actions">
          <button className="btn btn-signal" type="button" onClick={() => setOpen(true)}>
            Track account
          </button>
        </div>
      </div>
      <div className="page">
        <div className="page-head">
          <div>
            <h1 className="display">Whole accounts.</h1>
            <p className="lede">
              Origin GitHub user or org. Dest ({overview?.dest_account || 'DEST_GITHUB_ACCOUNT'}) only receives
              new repos and new commits — not a full clone of what already exists.
            </p>
          </div>
        </div>
        {accounts.length === 0 ? (
          <div className="panel empty">
            <Schema />
            <h2>No accounts yet</h2>
            <p>Add an origin GitHub login. Existing repos are watched, not copied.</p>
            <button className="btn btn-signal" type="button" onClick={() => setOpen(true)}>
              Track an account
            </button>
          </div>
        ) : (
          <div className="cards">
            {accounts.map((account) => (
              <PairCard key={account.id} account={account} />
            ))}
          </div>
        )}
      </div>
      <RelayDrawer open={open} onClose={() => setOpen(false)} onSubmit={create} />
    </>
  )
}
