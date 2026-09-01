import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from './api'
import type { Account, CommitItem, LiveEvent, Overview } from './types'

type Toast = { id: number; text: string; bad?: boolean }

type Store = {
  overview: Overview | null
  accounts: Account[]
  activity: CommitItem[]
  loading: boolean
  now: number
  toasts: Toast[]
  refresh: () => Promise<void>
  dropAccount: (id: number) => void
  toast: (text: string, bad?: boolean) => void
}

const Ctx = createContext<Store | null>(null)

let toastId = 1

export function StoreProvider({ children }: { children: ReactNode }) {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [activity, setActivity] = useState<CommitItem[]>([])
  const [loading, setLoading] = useState(true)
  const [toasts, setToasts] = useState<Toast[]>([])
  const [now, setNow] = useState(() => Date.now())

  const toast = useCallback((text: string, bad = false) => {
    const id = toastId++
    setToasts((cur) => [...cur, { id, text, bad }])
    window.setTimeout(() => {
      setToasts((cur) => cur.filter((t) => t.id !== id))
    }, 3200)
  }, [])

  const refresh = useCallback(async () => {
    const [ov, list, act] = await Promise.all([api.overview(), api.accounts(), api.activity()])
    setOverview(ov)
    setAccounts(list)
    setActivity(act)
  }, [])

  const dropAccount = useCallback((id: number) => {
    setAccounts((cur) => cur.filter((row) => row.id !== id))
    setActivity((cur) => cur.filter((row) => row.account_id !== id))
  }, [])

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    refresh()
      .catch((err: Error) => toast(err.message, true))
      .finally(() => setLoading(false))
  }, [refresh, toast])

  useEffect(() => {
    let source: EventSource | null = null
    let closed = false

    const connect = () => {
      if (closed) return
      source = new EventSource('/api/events')
      source.onmessage = (message) => {
        try {
          const payload = JSON.parse(message.data) as LiveEvent
          const next = payload.data?.next_tick_at
          const paused = payload.data?.github_paused_until
          const remaining = payload.data?.github_remaining
          if (typeof next === 'string' || typeof paused === 'string' || typeof remaining === 'number') {
            setOverview((cur) =>
              cur
                ? {
                    ...cur,
                    ...(typeof next === 'string' ? { next_tick_at: next } : {}),
                    ...(typeof paused === 'string' ? { github_paused_until: paused } : {}),
                    ...(typeof remaining === 'number' ? { github_remaining: remaining } : {}),
                  }
                : cur,
            )
          }
          if (payload.event === 'rate_limit') {
            const origin = String(payload.data?.origin || 'origin')
            toast(`GitHub rate limit on ${origin}`, true)
            void refresh()
            return
          }
          if (payload.event === 'hello' || payload.event === 'tick') return
          void refresh()
        } catch {
          /* ignore malformed frames */
        }
      }
      source.onerror = () => {
        source?.close()
        window.setTimeout(connect, 2500)
      }
    }
    connect()
    return () => {
      closed = true
      source?.close()
    }
  }, [refresh])

  const value = useMemo(
    () => ({ overview, accounts, activity, loading, now, toasts, refresh, dropAccount, toast }),
    [overview, accounts, activity, loading, now, toasts, refresh, dropAccount, toast],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useStore() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('store missing')
  return ctx
}
