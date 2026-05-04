export interface PageMeta {
  title: string
  created: string | null
  updated: string | null
  tags: string[]
}

export interface PageWrite {
  body: string
}

export interface PageMove {
  new_path: string
}

export interface PageRead {
  path: string
  meta: PageMeta
  body: string
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
  source_id?: string | null
}

export interface AssetUploadResponse {
  filename: string
  size: number
  sha256: string
  kind: 'image' | 'file'
  deduped: boolean
}

export interface WatchedFolder {
  label: string
  path: string
  exists: boolean
}

export interface WatchedFolderCreate {
  label: string
  path: string
}

// ---- Git sources -------------------------------------------------------

export interface GitSource {
  id: string
  label: string
  remote_url: string
  branch: string
  ssh_key_id: string | null
  http_username: string | null
  sync_interval_minutes: number
  local_path: string
  cloned: boolean
  last_synced_at: string | null
  last_sync_error: string | null
}

export interface GitSourceCreate {
  id: string
  label: string
  remote_url: string
  branch?: string
  ssh_key_id?: string | null
  http_username?: string | null
  http_password?: string | null
  sync_interval_minutes?: number
}

export interface GitSourceUpdate {
  label?: string
  branch?: string
  ssh_key_id?: string | null
  http_username?: string | null
  http_password?: string | null
  sync_interval_minutes?: number
}

export interface SshKey {
  id: string
  label: string
  fingerprint: string
}

export interface SshKeyCreate {
  label: string
  private_key: string
}
