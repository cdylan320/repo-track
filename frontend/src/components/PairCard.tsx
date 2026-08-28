import { Link } from 'react-router-dom'
import type { Account } from '../types'
import { Conduit, PairTime, StatusTag } from './PairVisual'

export function PairCard({ account }: { account: Account }) {
  return (
    <Link to={`/accounts/${account.id}`} className="card">
      <div className="card-top">
        <StatusTag account={account} />
        <span className="muted mono" style={{ fontSize: 12 }}>
          <PairTime account={account} />
        </span>
      </div>
      <Conduit account={account} />
      <div className="card-foot">
        <span>{account.repo_count} repos</span>
        <span>{account.commits_synced} relayed</span>
      </div>
    </Link>
  )
}
