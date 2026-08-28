import { Link } from 'react-router-dom'
import type { CommitItem } from '../types'
import { clockTime, firstLine, relativeTime } from '../format'
import { useStore } from '../store'

export function CommitRow({ item, toPair }: { item: CommitItem; toPair?: boolean }) {
  const { now } = useStore()
  const files = (item.files_list || '')
    .split(', ')
    .filter(Boolean)
    .slice(0, 4)
  return (
    <div className="commit">
      <div className="sha">{item.short_sha}</div>
      <div>
        <div className="msg">{firstLine(item.message)}</div>
        <div className="sub">
          {item.repo_name ? <span className="mono">{item.repo_name} · </span> : null}
          {item.author_name || 'unknown'}
          {' · '}
          {relativeTime(item.authored_at || item.synced_at, now)}
          {item.files_changed ? ` · ${item.files_changed} files` : ''}
          {item.insertions ? (
            <>
              {' '}
              <span className="stat-plus">+{item.insertions}</span>
            </>
          ) : null}
          {item.deletions ? (
            <>
              {' '}
              <span className="stat-minus">−{item.deletions}</span>
            </>
          ) : null}
          {toPair ? (
            <>
              {' · '}
              <Link to={`/accounts/${item.account_id}`}>{item.origin_label}</Link>
            </>
          ) : null}
        </div>
        {files.length ? (
          <div className="file-row">
            {files.map((f) => (
              <span key={f} className="file-chip">
                {f}
              </span>
            ))}
          </div>
        ) : null}
        <div className="sub muted">synced {clockTime(item.synced_at)}</div>
      </div>
    </div>
  )
}

export function CommitFeed({ items, toPair }: { items: CommitItem[]; toPair?: boolean }) {
  if (!items.length) {
    return (
      <div className="empty">
        <p className="muted">No commits have been relayed yet.</p>
      </div>
    )
  }
  return (
    <div className="feed">
      {items.map((item) => (
        <CommitRow key={item.id} item={item} toPair={toPair} />
      ))}
    </div>
  )
}
