import { countdown } from '../format'
import { useStore } from '../store'

export function RateLimitBanner() {
  const { overview, now } = useStore()
  const paused = overview?.github_paused_until
  const limited = overview?.rate_limited_count ?? 0
  const pausedActive = paused && countdown(paused, now) !== 'now'

  if (!pausedActive && limited <= 0) return null

  return (
    <div className="rate-banner" role="alert">
      <strong>GitHub rate limit</strong>
      {limited > 0 ? (
        <span>
          {' '}
          — {limited} origin{limited === 1 ? '' : 's'} cannot poll right now
        </span>
      ) : null}
      {pausedActive ? <span> · resumes {countdown(paused, now)}</span> : null}
      {overview?.github_remaining != null ? (
        <span>
          {' '}
          · {overview.github_remaining} API calls left
        </span>
      ) : null}
    </div>
  )
}
