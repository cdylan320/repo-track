import { CommitFeed } from '../components/CommitFeed'
import { useStore } from '../store'

export function ActivityPage() {
  const { activity } = useStore()
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
        </div>
        <div className="timeline panel">
          <CommitFeed items={activity} toPair />
        </div>
      </div>
    </>
  )
}
