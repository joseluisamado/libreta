import type {
  AssetUploadResponse,
  DiffEntry,
  GitSource,
  GitSourceCreate,
  GitSourceUpdate,
  HistoryEntry,
  PageMove,
  PageNode,
  PageRead,
  PageWrite,
  RecentChange,
  SearchResult,
  SshKey,
  SshKeyCreate,
  WatchedFolder,
  WatchedFolderCreate,
} from './types'

const BASE = '/api/v1'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, init)
  if (!r.ok) {
    const body = (await r.json().catch(() => ({}))) as { detail?: string }
    throw new Error(body.detail ?? `HTTP ${r.status}`)
  }
  return (await r.json()) as T
}

export function getTree(): Promise<PageNode[]> {
  return request<PageNode[]>('/pages/tree')
}

export function getRecentChanges(limit = 20): Promise<RecentChange[]> {
  const qs = new URLSearchParams({ limit: String(limit) }).toString()
  return request<RecentChange[]>(`/pages/recent?${qs}`)
}

export function getPage(path: string): Promise<PageRead> {
  return request<PageRead>(`/pages/${path}`)
}

export function savePage(path: string, data: PageWrite): Promise<PageRead> {
  return request<PageRead>(`/pages/${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

async function requestNoContent(path: string, init?: RequestInit): Promise<void> {
  const r = await fetch(`${BASE}${path}`, init)
  if (!r.ok) {
    const body = (await r.json().catch(() => ({}))) as { detail?: string }
    throw new Error(body.detail ?? `HTTP ${r.status}`)
  }
}

export function deletePage(path: string): Promise<void> {
  return requestNoContent(`/pages/${path}`, { method: 'DELETE' })
}

export function getPageHistory(path: string): Promise<HistoryEntry[]> {
  return request<HistoryEntry[]>(`/pages/${path}/history`)
}

export function getPageDiff(path: string, a: string, b: string): Promise<DiffEntry> {
  const qs = new URLSearchParams({ a, b }).toString()
  return request<DiffEntry>(`/pages/${path}/diff?${qs}`)
}

export async function uploadAsset(pagePath: string, file: File): Promise<AssetUploadResponse> {
  const fd = new FormData()
  fd.append('file', file, file.name)
  // Don't set Content-Type — the browser sets it (with the boundary).
  const r = await fetch(`${BASE}/pages/${pagePath}/assets`, { method: 'POST', body: fd })
  if (!r.ok) {
    const body = (await r.json().catch(() => ({}))) as { detail?: string }
    throw new Error(body.detail ?? `HTTP ${r.status}`)
  }
  return (await r.json()) as AssetUploadResponse
}

export function searchPages(q: string, limit = 20): Promise<SearchResult[]> {
  const qs = new URLSearchParams({ q, limit: String(limit) }).toString()
  return request<SearchResult[]>(`/search?${qs}`)
}

export function movePage(path: string, data: PageMove): Promise<PageRead> {
  return request<PageRead>(`/pages/${path}/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

// ---- Watch folder API --------------------------------------------------------

export function getWatchedFolders(): Promise<WatchedFolder[]> {
  return request<WatchedFolder[]>('/watch/folders')
}

export function addWatchedFolder(data: WatchedFolderCreate): Promise<WatchedFolder> {
  return request<WatchedFolder>('/watch/folders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function removeWatchedFolder(label: string): Promise<void> {
  return requestNoContent(`/watch/folders/${label}`, { method: 'DELETE' })
}

export function getWatchedTree(label: string): Promise<PageNode[]> {
  return request<PageNode[]>(`/watch/${label}/tree`)
}

export function getWatchedPage(label: string, path: string): Promise<PageRead> {
  return request<PageRead>(`/watch/${label}/${path}`)
}

export function saveWatchedPage(label: string, path: string, data: PageWrite): Promise<PageRead> {
  return request<PageRead>(`/watch/${label}/${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

// ---- SSH keys API -------------------------------------------------------

export function getSshKeys(): Promise<SshKey[]> {
  return request<SshKey[]>('/sources/keys')
}

export function addSshKey(data: SshKeyCreate): Promise<SshKey> {
  return request<SshKey>('/sources/keys', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function deleteSshKey(keyId: string): Promise<void> {
  return requestNoContent(`/sources/keys/${keyId}`, { method: 'DELETE' })
}

// ---- Git sources API ----------------------------------------------------

export function getSources(): Promise<GitSource[]> {
  return request<GitSource[]>('/sources')
}

export function addSource(data: GitSourceCreate): Promise<GitSource> {
  return request<GitSource>('/sources', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function updateSource(id: string, data: GitSourceUpdate): Promise<GitSource> {
  return request<GitSource>(`/sources/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function deleteSource(id: string): Promise<void> {
  return requestNoContent(`/sources/${id}`, { method: 'DELETE' })
}

export function triggerSync(id: string): Promise<GitSource> {
  return request<GitSource>(`/sources/${id}/sync`, { method: 'POST' })
}

export function getSourceTree(id: string): Promise<PageNode[]> {
  return request<PageNode[]>(`/sources/${id}/tree`)
}

export function getSourcePage(id: string, path: string): Promise<PageRead> {
  return request<PageRead>(`/sources/${id}/pages/${path}`)
}

export function saveSourcePage(id: string, path: string, data: PageWrite): Promise<PageRead> {
  return request<PageRead>(`/sources/${id}/pages/${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}
