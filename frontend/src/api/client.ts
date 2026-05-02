import type { DiffEntry, HistoryEntry, PageMove, PageNode, PageRead, PageWrite } from './types'

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

export function movePage(path: string, data: PageMove): Promise<PageRead> {
  return request<PageRead>(`/pages/${path}/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}
