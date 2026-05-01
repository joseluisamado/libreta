import type { PageNode, PageRead } from './types'

const BASE = '/api/v1'

async function request<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`)
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
