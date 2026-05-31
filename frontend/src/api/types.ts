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

export interface OtherFile {
  name: string
  path: string
  kind: 'image' | 'drawio' | 'text' | 'binary'
}

export interface DirChildren {
  children: PageNode[]
  other_files: OtherFile[]
}

export interface PageNode {
  path: string
  title: string // H1 of the markdown body, or beautified stem fallback
  filename: string // sidebar label / on-disk filename including extension (e.g. "foo.md", "diagram.pdf")
  is_directory: boolean
  children: PageNode[]
  has_more?: boolean
  kind?: 'page' | 'pdf'
  other_files?: OtherFile[]
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
  // When set, the source clones/fetches/pushes using the token stored for
  // this Gitea server (see GiteaServer).
  gitea_server_id: string | null
  sync_interval_minutes: number
  local_path: string
  cloned: boolean
  last_synced_at: string | null
  last_sync_error: string | null
  // Number of local commits ahead of origin/<branch>. The sidebar dot turns
  // amber when this is > 0; clicking the source's "↑N" link fetches the
  // detailed PendingCommit list.
  pending_count: number
}

export interface PendingCommit {
  sha: string
  message: string
  author: string
  timestamp: string
  // .md page paths (no .md suffix) touched by the commit.
  paths: string[]
}

export interface GitSourceCreate {
  id: string
  label: string
  remote_url: string
  branch?: string
  ssh_key_id?: string | null
  http_username?: string | null
  http_password?: string | null
  gitea_server_id?: string | null
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

// ---- Gitea servers (remembered credential groups) -----------------------

export interface GiteaServer {
  id: string
  label: string
  base_url: string
  username: string
}

export interface GiteaServerCreate {
  label: string
  base_url: string
  username: string
  token: string
}

export interface GiteaRepo {
  name: string
  full_name: string
  clone_url: string
  description: string
  empty: boolean
  // True when a source already tracks this clone_url.
  already_added: boolean
}

export interface GiteaImportRequest {
  owner: string
  repos: string[]
}
