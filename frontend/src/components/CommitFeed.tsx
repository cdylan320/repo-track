import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { CommitItem } from '../types'
import { clockTime, firstLine, relativeTime } from '../format'
import { useStore } from '../store'

function RepoLink({ href, title, children }: { href: string; title?: string; children: ReactNode }) {
  if (!href) return <>{children}</>
  return (
    <a className="ext" href={href} target="_blank" rel="noreferrer" title={title}>
      {children}
    </a>
  )
}

export function CommitRow({ item, toPair }: { item: CommitItem; toPair?: boolean }) {
  const { now } = useStore()
  if (item.kind === 'new-repo') {
    return <NewRepoRow item={item} toPair={toPair} />
  }
  const files = (item.files_list || '')
    .split(', ')
    .filter(Boolean)
    .slice(0, 4)
  const commitUrl = item.origin_url && item.sha ? `${item.origin_url}/commit/${item.sha}` : ''
  return (
    <div className="commit">
      <div className="sha">
        <RepoLink href={commitUrl} title={`Open ${item.short_sha} on origin`}>
          {item.short_sha}
        </RepoLink>
      </div>
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
        <div className="sub muted">
          synced {clockTime(item.synced_at)}
          <RepoRefs item={item} />
        </div>
      </div>
    </div>
  )
}

function RepoRefs({ item }: { item: CommitItem }) {
  if (!item.origin_url && !item.dest_url) return null
  return (
    <>
      {item.origin_url ? (
        <>
          {' · '}
          <RepoLink href={item.origin_url} title={item.origin_label}>
            origin ↗
          </RepoLink>
        </>
      ) : null}
      {item.dest_url ? (
        <>
          {' · '}
          <RepoLink href={item.dest_url} title={item.dest_label}>
            dest ↗
          </RepoLink>
        </>
      ) : null}
    </>
  )
}

function NewRepoRow({ item, toPair }: { item: CommitItem; toPair?: boolean }) {
  const { now } = useStore()
  const pair = item.origin_label.includes('/') && item.dest_label.includes('/')
  return (
    <div className="commit">
      <div className="kind new-repo">new-repo</div>
      <div>
        <div className="msg">
          {pair ? (
            <>
              New repo{' '}
              <RepoLink href={item.origin_url} title="Open origin repo on GitHub">
                {item.origin_label}
              </RepoLink>
              {' → '}
              <RepoLink href={item.dest_url} title="Open dest repo on GitHub">
                {item.dest_label}
              </RepoLink>
            </>
          ) : (
            firstLine(item.message)
          )}
        </div>
        <div className="sub">
          {item.repo_name ? <span className="mono">{item.repo_name} · </span> : null}
          opened on dest · {relativeTime(item.authored_at || item.synced_at, now)}
          {toPair && item.account_id ? (
            <>
              {' · '}
              <Link to={`/accounts/${item.account_id}`}>{item.origin_label || item.dest_label}</Link>
            </>
          ) : null}
        </div>
        <div className="sub muted">opened {clockTime(item.synced_at)}</div>
      </div>
    </div>
  )
}

export function CommitFeed({
  items,
  toPair,
  emptyMessage,
}: {
  items: CommitItem[]
  toPair?: boolean
  emptyMessage?: string
}) {
  if (!items.length) {
    return (
      <div className="empty">
        <p className="muted">{emptyMessage || 'Nothing has moved yet.'}</p>
      </div>
    )
  }
  return (
    <div className="feed">
      {items.map((item) => (
        <CommitRow key={`${item.kind || 'commit'}-${item.id}`} item={item} toPair={toPair} />
      ))}
    </div>
  )
}
