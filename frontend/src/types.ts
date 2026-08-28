export type Account = {
  id: number
  origin_account: string
  origin_kind: string
  dest_account: string
  name: string
  sync_mode: 'ff-only' | 'force'
  include_forks: boolean
  paused: boolean
  status: 'idle' | 'syncing' | 'error' | string
  last_error: string
  last_sync_at: string | null
  created_at: string
  updated_at: string
  repo_count: number
  commits_synced: number
  commits_today: number
  repos: RepoItem[]
}

export type RepoItem = {
  id: number
  account_id: number
  name: string
  origin_url: string
  dest_url: string
  default_branch: string
  private: boolean
  mirrored: boolean
  last_sha: string
  last_sync_at: string | null
  last_error: string
  status: string
  commits_synced: number
}

export type AccountDraft = {
  origin_account: string
  name: string
  sync_mode: 'ff-only' | 'force'
  include_forks: boolean
}

export type CommitItem = {
  id: number
  account_id: number
  repo_id: number
  pair_id?: number
  sha: string
  short_sha: string
  message: string
  author_name: string
  author_email: string
  authored_at: string | null
  files_changed: number
  insertions: number
  deletions: number
  files_list: string
  synced_at: string
  origin_label: string
  dest_label: string
  repo_name: string
  account_name: string
}

export type LogItem = {
  id: number
  account_id: number | null
  pair_id?: number | null
  repo_id: number | null
  kind: string
  message: string
  detail: string
  created_at: string
  origin_label: string
  dest_label: string
}

export type Overview = {
  account_count: number
  pair_count: number
  active_count: number
  paused_count: number
  error_count: number
  repo_count: number
  commits_today: number
  commits_total: number
  last_sync_at: string | null
  poll_interval_seconds: number
  discord_configured: boolean
  dest_account: string
  dest_token_configured: boolean
  origin_token_configured: boolean
  git_token_configured: boolean
  worker_running: boolean
  next_tick_at: string | null
}

export type Settings = {
  poll_interval_seconds: number
  discord_configured: boolean
  discord_webhook_hint: string
  dest_account: string
  dest_token_configured: boolean
  dest_token_hint: string
  origin_token_configured: boolean
  origin_token_hint: string
  git_token_configured: boolean
  git_token_hint: string
}

export type LiveEvent = {
  event: string
  data: Record<string, unknown>
}
