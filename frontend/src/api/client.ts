import type {
  AssetUploadResponse,
  DiffEntry,
  HistoryEntry,
  PageMove,
  PageNode,
  PageRead,
  PageWrite,
  SearchResult,
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
