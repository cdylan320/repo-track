import type { Account, AccountDraft, CommitItem, LogItem, Overview, Settings, SettingsDraft } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const { signal, headers, ...rest } = init ?? {}
  const long = /\/sync(?:-all)?$/.test(path)
  const response = await fetch(path, {
    ...rest,
    headers: { 'Content-Type': 'application/json', ...(headers as Record<string, string> | undefined) },
    signal: signal ?? AbortSignal.timeout(long ? 300000 : 8000),
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body.detail || body.message || JSON.stringify(body)
    } catch {
      detail = await response.text()
    }
    throw new Error(typeof detail === 'string' ? detail : 'Request failed')
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

export const api = {
  overview: () => request<Overview>('/api/overview'),
  accounts: () => request<Account[]>('/api/accounts'),
  account: (id: number) => request<Account>(`/api/accounts/${id}`),
  createAccount: (body: AccountDraft) =>
    request<Account>('/api/accounts', { method: 'POST', body: JSON.stringify(body) }),
  updateAccount: (id: number, body: Partial<AccountDraft> & { paused?: boolean }) =>
    request<Account>(`/api/accounts/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteAccount: (id: number) => request<{ ok: boolean }>(`/api/accounts/${id}`, { method: 'DELETE' }),
  syncAccount: (id: number) =>
    request<{ ok: boolean; count: number; account: Account }>(`/api/accounts/${id}/sync`, { method: 'POST' }),
  syncAll: () => request<{ ok: boolean }>('/api/accounts/sync-all', { method: 'POST' }),
  activity: (accountId?: number) =>
    request<CommitItem[]>(accountId ? `/api/activity?account_id=${accountId}` : '/api/activity'),
  clearActivity: () =>
    request<{ ok: boolean; commits_deleted: number; events_deleted: number }>('/api/activity', {
      method: 'DELETE',
    }),
  logs: (accountId?: number) =>
    request<LogItem[]>(accountId ? `/api/logs?account_id=${accountId}` : '/api/logs'),
  settings: () => request<Settings>('/api/settings'),
  updateSettings: (body: SettingsDraft) =>
    request<Settings>('/api/settings', { method: 'PATCH', body: JSON.stringify(body) }),
  testDiscord: () => request<{ ok: boolean; message: string }>('/api/settings/discord-test', { method: 'POST' }),
}
