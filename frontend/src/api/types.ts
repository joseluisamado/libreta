export interface PageMeta {
  title: string
  created: string | null
  updated: string | null
  tags: string[]
}

export interface PageWrite {
  body: string
  is_index?: boolean
}

export interface PageMove {
  new_path: string
}

export interface PageRead {
  path: string
  meta: PageMeta
  body: string
  is_index: boolean
}

export interface PageNode {
  path: string
  title: string
  is_directory: boolean
  children: PageNode[]
}

export interface HistoryEntry {
  sha: string
  message: string
  author: string
  timestamp: string
}

export interface DiffEntry {
  old_sha: string
  new_sha: string
  old_path: string | null
  new_path: string | null
  patch: string
}

export interface RecentChange {
  sha: string
  message: string
  author: string
  timestamp: string
  path: string
}

export interface ApiError {
  error: string
  detail: string
}

export interface SearchResult {
  path: string
  title: string
  snippet: string
  updated: string
  tags: string
}

export interface AssetUploadResponse {
  filename: string
  size: number
  sha256: string
  kind: 'image' | 'file'
  deduped: boolean
}
