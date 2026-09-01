import { useEffect, useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import { countdown } from '../format'
import type { Settings } from '../types'

export function SettingsPage() {
  const { refresh, toast, now } = useStore()
  const [settings, setSettings] = useState<Settings | null>(null)
  const [interval, setIntervalSec] = useState(60)
  const [saving, setSaving] = useState(false)
  const [pinging, setPinging] = useState(false)

  useEffect(() => {
    api
      .settings()
      .then((s) => {
        setSettings(s)
        setIntervalSec(s.poll_interval_seconds)
      })
      .catch((err: Error) => toast(err.message, true))
  }, [toast])

  async function save() {
    setSaving(true)
    try {
      const next = await api.updateSettings(interval)
      setSettings(next)
      await refresh()
      toast('Poll interval updated')
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Save failed', true)
    } finally {
      setSaving(false)
    }
  }

  async function ping() {
    setPinging(true)
    try {
      await api.testDiscord()
      toast('Test message sent to Discord')
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Discord test failed', true)
    } finally {
      setPinging(false)
    }
  }

  const recommended = settings?.recommended_poll_seconds ?? 10

  return (
    <>
      <div className="topbar">
        <span className="crumb">Settings</span>
      </div>
      <div className="page">
        <div className="page-head">
          <div>
            <h1 className="display">How Relay runs.</h1>
            <p className="lede">Tokens and poll tuning live in .env. Interval can be changed here.</p>
          </div>
        </div>
        <div className="settings-grid">
          <section className="block">
            <h3>Poll interval</h3>
            <p>
              Every poll checks <strong>all</strong> origin accounts in parallel. Recommended for your setup:{' '}
              <strong>{recommended}s</strong> (based on account count and poll-token buckets).
            </p>
            <input
              className="range"
              type="range"
              min={2}
              max={600}
              step={1}
              value={interval}
              onChange={(e) => setIntervalSec(Number(e.target.value))}
            />
            <div className="sub" style={{ marginBottom: 16 }}>
              Every <span className="mono">{interval}s</span> for every origin
              {interval < recommended ? (
                <span className="warn"> · below recommended — higher rate-limit risk</span>
              ) : null}
            </div>
            <button className="btn btn-signal" type="button" onClick={save} disabled={saving}>
              {saving ? 'Saving…' : 'Save interval'}
            </button>
          </section>
          <section className="block">
            <h3>Poll tokens (.env)</h3>
            <p>
              <code>POLL_TOKENS</code> — comma-separated; one token assigned per origin (round-robin).{' '}
              <code>POLL_TOKEN_MAP</code> — explicit <code>login:token</code> pairs. Best if each token is on a{' '}
              <strong>different GitHub user</strong> (separate 5000/hr buckets).
            </p>
            <div className="sub">
              pool {settings?.poll_tokens_configured || 0} · map {settings?.poll_token_map_configured || 0} · dest{' '}
              {settings?.dest_tokens_configured || 0}
            </div>
            {settings?.github_buckets?.length ? (
              <div className="bucket-list">
                {settings.github_buckets.map((bucket) => (
                  <div key={bucket.key} className={`bucket-row${bucket.paused_until ? ' warn' : ''}`}>
                    <span className="mono">{bucket.hint || bucket.key}</span>
                    <span>{bucket.remaining} left</span>
                    {bucket.paused_until ? (
                      <span>pause {countdown(bucket.paused_until, now)}</span>
                    ) : bucket.accounts.length ? (
                      <span>{bucket.accounts.join(', ')}</span>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : null}
          </section>
          <section className="block">
            <h3>Discord</h3>
            <p>
              Every poll checks rate limits for <strong>all</strong> origins. The UI banner and sidebar update every
              poll cycle. Discord/toast fire once when a limit first hits (not repeated every cycle while blocked).
            </p>
            <div className="token">{settings?.discord_configured ? settings.discord_webhook_hint : 'not configured'}</div>
            <div style={{ marginTop: 16 }}>
              <button className="btn" type="button" onClick={ping} disabled={pinging || !settings?.discord_configured}>
                {pinging ? 'Sending…' : 'Send test'}
              </button>
            </div>
          </section>
          <section className="block">
            <h3>Destination GitHub</h3>
            <p>
              <code>DEST_GITHUB_TOKEN</code> or <code>DEST_GITHUB_TOKENS</code> — create/push dest repos. Falls back as
              poll token when no <code>POLL_TOKENS</code> are set.
            </p>
            <div className="token">{settings?.dest_account || 'not configured'}</div>
            <div className="sub" style={{ marginTop: 8 }}>
              token {settings?.dest_token_configured ? settings.dest_token_hint : 'missing'}
            </div>
          </section>
          <section className="block">
            <h3>Origin token</h3>
            <p>Optional <code>GITHUB_TOKEN</code>. Only needed for private origin repos.</p>
            <div className="token">{settings?.origin_token_configured ? settings.origin_token_hint : 'public repos only'}</div>
          </section>
        </div>
      </div>
    </>
  )
}
