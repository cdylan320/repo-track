import { useMemo, useState } from 'react'
import { CommitFeed } from '../components/CommitFeed'
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
  const { activity } = useStore()
  const [query, setQuery] = useState('')
  const filtered = useMemo(
    () => activity.filter((item) => matchesQuery(item, query)),
    [activity, query],
  )
  const trimmed = query.trim()

  return (
    <>
      <div className="topbar">
        <span className="crumb">Activity</span>
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
    </>
  )
}
