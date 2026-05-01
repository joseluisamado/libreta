export interface PageMeta {
  title: string
  created: string | null
  updated: string | null
  tags: string[]
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

export interface ApiError {
  error: string
  detail: string
}
