import { useEffect, useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import type { Settings } from '../types'

export function SettingsPage() {
  const { refresh, toast } = useStore()
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

  return (
    <>
      <div className="topbar">
        <span className="crumb">Settings</span>
      </div>
      <div className="page">
        <div className="page-head">
          <div>
            <h1 className="display">How Relay runs.</h1>
            <p className="lede">Dest account and tokens stay in .env. Tune the poll from here.</p>
          </div>
        </div>
        <div className="settings-grid">
          <section className="block">
            <h3>Poll interval</h3>
            <p>
              Every poll checks <strong>all</strong> origin accounts in parallel. Dest token is used only to create/push
              dest repos — origin change detection is public GitHub (or optional GITHUB_TOKEN for private origin).
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
            </div>
            <button className="btn btn-signal" type="button" onClick={save} disabled={saving}>
              {saving ? 'Saving…' : 'Save interval'}
            </button>
          </section>
          <section className="block">
            <h3>Discord</h3>
            <p>One compact note per account when something actually moved: new repos, commit subject, files, +/−.</p>
            <div className="token">{settings?.discord_configured ? settings.discord_webhook_hint : 'not configured'}</div>
            <div style={{ marginTop: 16 }}>
              <button className="btn" type="button" onClick={ping} disabled={pinging || !settings?.discord_configured}>
                {pinging ? 'Sending…' : 'Send test'}
              </button>
            </div>
          </section>
          <section className="block">
            <h3>Destination GitHub</h3>
            <p>DEST_GITHUB_ACCOUNT and DEST_GITHUB_TOKEN. Used only when origin actually changes.</p>
            <div className="token">{settings?.dest_account || 'not configured'}</div>
            <div className="sub" style={{ marginTop: 8 }}>
              token {settings?.dest_token_configured ? settings.dest_token_hint : 'missing'}
            </div>
          </section>
          <section className="block">
            <h3>Origin token</h3>
            <p>Optional GITHUB_TOKEN. Needed only if the origin account has private repos you want mirrored.</p>
            <div className="token">{settings?.origin_token_configured ? settings.origin_token_hint : 'public repos only'}</div>
          </section>
        </div>
      </div>
    </>
  )
}
