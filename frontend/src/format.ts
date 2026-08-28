export function parseAccount(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, '')
  if (!trimmed) return ''
  if (trimmed.startsWith('git@github.com:')) return trimmed.split(':')[1]?.split('/')[0] ?? ''
  try {
    const withProto = trimmed.includes('://') ? trimmed : trimmed.includes('github.com') ? `https://${trimmed}` : ''
    if (withProto) {
      const path = new URL(withProto).pathname.replace(/^\//, '')
      return path.split('/')[0] || ''
    }
  } catch {
    return trimmed.split('/')[0]
  }
  return trimmed.split('/')[0]
}

export function repoLabel(url: string): string {
  const trimmed = url.trim()
  if (!trimmed) return ''
  if (trimmed.startsWith('git@')) {
    const match = trimmed.match(/git@[^:]+:(.+?)(?:\.git)?$/)
    return match ? match[1].replace(/\/$/, '') : trimmed
  }
  try {
    const parsed = new URL(trimmed)
    return parsed.pathname.replace(/^\//, '').replace(/\.git$/, '')
  } catch {
    return trimmed
  }
}

export function repoHost(url: string): string {
  const trimmed = url.trim()
  if (!trimmed) return ''
  if (trimmed.startsWith('git@')) {
    const match = trimmed.match(/git@([^:]+):/)
    return match?.[1] ?? 'git'
  }
  try {
    return new URL(trimmed).hostname
  } catch {
    return ''
  }
}

export function firstLine(message: string): string {
  return (message || '').split('\n')[0] || '—'
}

export function relativeTime(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return 'never'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'
  const seconds = Math.round((now - then) / 1000)
  const abs = Math.abs(seconds)
  if (abs < 10) return seconds >= 0 ? 'just now' : 'soon'
  if (abs < 60) return seconds >= 0 ? `${abs}s ago` : `in ${abs}s`
  const minutes = Math.round(abs / 60)
  if (minutes < 60) return seconds >= 0 ? `${minutes}m ago` : `in ${minutes}m`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return seconds >= 0 ? `${hours}h ago` : `in ${hours}h`
  const days = Math.round(hours / 24)
  return seconds >= 0 ? `${days}d ago` : `in ${days}d`
}

export function countdown(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'
  const remaining = Math.ceil((then - now) / 1000)
  if (remaining <= 0) return 'now'
  if (remaining < 60) return `in ${remaining}s`
  const minutes = Math.floor(remaining / 60)
  const seconds = remaining % 60
  if (minutes < 60) return seconds ? `in ${minutes}m ${seconds}s` : `in ${minutes}m`
  const hours = Math.floor(minutes / 60)
  return `in ${hours}h ${minutes % 60}m`
}

export function clockTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function todayLabel(): string {
  return new Date().toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
  })
}

export function splitRepo(label: string): { owner: string; name: string } {
  const parts = label.split('/').filter(Boolean)
  if (parts.length < 2) return { owner: '', name: label || 'repo' }
  return { owner: parts.slice(0, -1).join('/'), name: parts[parts.length - 1] }
}
