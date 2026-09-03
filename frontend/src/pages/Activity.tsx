import { useMemo, useState } from 'react'
import { api } from '../api'
import { CommitFeed } from '../components/CommitFeed'
import { Confirm } from '../components/Confirm'
import { useStore } from '../store'
import type { CommitItem } from '../types'

function matchesQuery(item: CommitItem, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  const hay = [
    item.repo_name,
    item.origin_label,
    item.dest_label,
    item.message,
    item.author_name,
    item.short_sha,
    item.sha,
    item.account_name,
    item.files_list,
    item.kind,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return hay.includes(q)
}

export function ActivityPage() {
  const { activity, refresh, toast } = useStore()
  const [query, setQuery] = useState('')
  const [confirmClear, setConfirmClear] = useState(false)
  const [clearing, setClearing] = useState(false)
  const filtered = useMemo(
    () => activity.filter((item) => matchesQuery(item, query)),
    [activity, query],
  )
  const trimmed = query.trim()

  async function clearHistory() {
    setClearing(true)
    try {
      await api.clearActivity()
      await refresh()
      setConfirmClear(false)
      toast('Activity history cleared')
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Clear failed', true)
    } finally {
      setClearing(false)
    }
  }

  return (
    <>
      <div className="topbar">
        <span className="crumb">Activity</span>
        <button
          className="btn btn-ghost btn-sm"
          type="button"
          disabled={!activity.length || clearing}
          onClick={() => setConfirmClear(true)}
        >
          Clear history
        </button>
      </div>
      <div className="page">
        <div className="page-head">
          <div>
            <h1 className="display">What moved.</h1>
            <p className="lede">New dest repos and commits Relay pushed after the baseline.</p>
          </div>
          <input
            className="activity-search"
            type="search"
            placeholder="Search repo, account, commit…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoComplete="off"
            spellCheck={false}
            aria-label="Search activity"
          />
        </div>
        <div className="timeline panel">
          <CommitFeed
            items={filtered}
            toPair
            emptyMessage={trimmed ? 'No activity matches that search.' : undefined}
          />
        </div>
      </div>
      <Confirm
        open={confirmClear}
        title="Clear all activity history?"
        body="Removes every commit and new-repo entry from the Activity feed. Tracking continues — dest repos are left alone."
        confirmLabel={clearing ? 'Clearing…' : 'Clear history'}
        onCancel={() => {
          if (!clearing) setConfirmClear(false)
        }}
        onConfirm={() => {
          if (!clearing) void clearHistory()
        }}
      />
    </>
  )
}
