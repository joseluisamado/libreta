import type {
  AssetUploadResponse,
  DiffEntry,
  DirChildren,
  GitSource,
  GitSourceCreate,
  GitSourceUpdate,
  HistoryEntry,
  PageMove,
  PageNode,
  PageRead,
  PageWrite,
  PendingCommit,
  RecentChange,
  SearchResult,
  SshKey,
  SshKeyCreate,
  WatchedFolder,
  WatchedFolderCreate,
} from './types'

const BASE = '/api/v1'

/** Encode each segment of a URL path so spaces and special chars are safe. */
function enc(path: string): string {
  return path.split('/').map(encodeURIComponent).join('/')
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, init)
  if (!r.ok) {
    const body = (await r.json().catch(() => ({}))) as { detail?: unknown }
    const detail = body.detail
    let message: string
    if (Array.isArray(detail)) {
      // Pydantic validation errors: [{loc, msg, ...}, ...]
      message = detail
        .map((e: { msg?: string; loc?: unknown[] }) => {
          const field = Array.isArray(e.loc) ? e.loc.slice(1).join('.') : ''
          return field ? `${field}: ${e.msg ?? ''}` : (e.msg ?? '')
        })
        .join('; ')
    } else {
      message = typeof detail === 'string' ? detail : `HTTP ${r.status}`
    }
    throw new Error(message)
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
  return request<PageRead>(`/pages/${enc(path)}`)
}

export function savePage(path: string, data: PageWrite): Promise<PageRead> {
  return request<PageRead>(`/pages/${enc(path)}`, {
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
  return requestNoContent(`/pages/${enc(path)}`, { method: 'DELETE' })
}

export function getPageHistory(path: string): Promise<HistoryEntry[]> {
  return request<HistoryEntry[]>(`/pages/${enc(path)}/history`)
}

export function getPageDiff(path: string, a: string, b: string): Promise<DiffEntry> {
  const qs = new URLSearchParams({ a, b }).toString()
  return request<DiffEntry>(`/pages/${enc(path)}/diff?${qs}`)
}

export async function uploadAsset(pagePath: string, file: File): Promise<AssetUploadResponse> {
  const fd = new FormData()
  fd.append('file', file, file.name)
  // Don't set Content-Type — the browser sets it (with the boundary).
  const r = await fetch(`${BASE}/pages/${enc(pagePath)}/assets`, { method: 'POST', body: fd })
  if (!r.ok) {
    const body = (await r.json().catch(() => ({}))) as { detail?: string }
    throw new Error(body.detail ?? `HTTP ${r.status}`)
  }
  return (await r.json()) as AssetUploadResponse
}

export async function uploadSourceAsset(
  sourceId: string,
  pagePath: string,
  file: File,
): Promise<AssetUploadResponse> {
  const fd = new FormData()
  fd.append('file', file, file.name)
  const r = await fetch(`${BASE}/sources/${sourceId}/pages/${enc(pagePath)}/assets`, {
    method: 'POST',
    body: fd,
  })
  if (!r.ok) {
    const body = (await r.json().catch(() => ({}))) as { detail?: string }
    throw new Error(body.detail ?? `HTTP ${r.status}`)
  }
  return (await r.json()) as AssetUploadResponse
}

export async function upsertAsset(
  pagePath: string,
  filename: string,
  data: Blob,
  contentType: string,
): Promise<AssetUploadResponse> {
  const fd = new FormData()
  fd.append('file', new File([data], filename, { type: contentType }), filename)
  const r = await fetch(`${BASE}/pages/${enc(pagePath)}/assets/${encodeURIComponent(filename)}`, {
    method: 'PUT',
    body: fd,
  })
  if (!r.ok) {
    const body = (await r.json().catch(() => ({}))) as { detail?: string }
    throw new Error(body.detail ?? `HTTP ${r.status}`)
  }
  return (await r.json()) as AssetUploadResponse
}

export async function upsertSourceAsset(
  sourceId: string,
  pagePath: string,
  filename: string,
  data: Blob,
  contentType: string,
): Promise<AssetUploadResponse> {
  const fd = new FormData()
  fd.append('file', new File([data], filename, { type: contentType }), filename)
  const r = await fetch(
    `${BASE}/sources/${sourceId}/pages/${enc(pagePath)}/assets/${encodeURIComponent(filename)}`,
    { method: 'PUT', body: fd },
  )
  if (!r.ok) {
    const body = (await r.json().catch(() => ({}))) as { detail?: string }
    throw new Error(body.detail ?? `HTTP ${r.status}`)
  }
  return (await r.json()) as AssetUploadResponse
}

export interface ClientConfig {
  drawio_url: string
}

export function getClientConfig(): Promise<ClientConfig> {
  return request<ClientConfig>('/config')
}

export function searchPages(q: string, limit = 20): Promise<SearchResult[]> {
  const qs = new URLSearchParams({ q, limit: String(limit) }).toString()
  return request<SearchResult[]>(`/search?${qs}`)
}

export function movePage(path: string, data: PageMove): Promise<PageRead> {
  return request<PageRead>(`/pages/${enc(path)}/move`, {
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
  return requestNoContent(`/watch/folders/${enc(label)}`, { method: 'DELETE' })
}

export function getWatchedTree(label: string): Promise<PageNode[]> {
  return request<PageNode[]>(`/watch/${enc(label)}/tree`)
}

export function getWatchedPage(label: string, path: string): Promise<PageRead> {
  return request<PageRead>(`/watch/${enc(label)}/${enc(path)}`)
}

export function saveWatchedPage(label: string, path: string, data: PageWrite): Promise<PageRead> {
  return request<PageRead>(`/watch/${enc(label)}/${enc(path)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function getWatchedChildren(label: string, path: string): Promise<DirChildren> {
  return request<DirChildren>(`/watch/${enc(label)}/children/${enc(path)}`)
}

export function createWatchedFolder(label: string, path: string): Promise<void> {
  return requestNoContent(`/watch/${enc(label)}/folders/${enc(path)}`, { method: 'POST' })
}

export function deleteWatchedPage(label: string, path: string): Promise<void> {
  return requestNoContent(`/watch/${enc(label)}/${enc(path)}`, { method: 'DELETE' })
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
  // The sidebar polls this endpoint to keep the per-source pending-count
  // dot honest. Some browsers (notably Safari) return a 200 from the
  // back/forward cache or the disk cache for plain GETs that look
  // idempotent; that makes the dot stick on a stale value even though
  // the backend has long since moved on. A timestamp cache-buster plus
  // `Cache-Control: no-store` defeats both layers.
  const t = Date.now()
  return request<GitSource[]>(`/sources?_t=${t}`, {
    headers: { 'Cache-Control': 'no-store' },
  })
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

export function getPendingCommits(id: string): Promise<PendingCommit[]> {
  return request<PendingCommit[]>(`/sources/${id}/pending`)
}

export function getSourceTree(id: string): Promise<PageNode[]> {
  return request<PageNode[]>(`/sources/${id}/tree`)
}

export function getSourceChildren(id: string, path: string): Promise<DirChildren> {
  return request<DirChildren>(`/sources/${id}/children/${enc(path)}`)
}

export function getSourcePage(id: string, path: string): Promise<PageRead> {
  return request<PageRead>(`/sources/${id}/pages/${enc(path)}`)
}

export function saveSourcePage(id: string, path: string, data: PageWrite): Promise<PageRead> {
  return request<PageRead>(`/sources/${id}/pages/${enc(path)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function deleteSourcePage(id: string, path: string): Promise<void> {
  return requestNoContent(`/sources/${id}/pages/${enc(path)}`, { method: 'DELETE' })
}

export function moveSourcePage(id: string, path: string, data: PageMove): Promise<PageRead> {
  return request<PageRead>(`/sources/${id}/pages/${enc(path)}/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function createSourceFolder(id: string, folderPath: string): Promise<void> {
  await requestNoContent(`/sources/${id}/folders/${enc(folderPath)}`, { method: 'POST' })
}
