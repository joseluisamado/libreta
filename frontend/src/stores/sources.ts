import { defineStore } from 'pinia'
import {
  getSources,
  addSource,
  updateSource,
  deleteSource,
  triggerSync,
  getSourceTree,
  getSourceChildren,
  getSshKeys,
  addSshKey,
  deleteSshKey,
} from '@/api/client'
import type { GitSource, GitSourceCreate, GitSourceUpdate, PageNode, SshKey, SshKeyCreate } from '@/api/types'

function mergeChildren(nodes: PageNode[], parentPath: string, children: PageNode[]): boolean {
  for (const n of nodes) {
    if (n.path === parentPath) {
      n.children = children
      n.has_more = false
      return true
    }
    if (n.children?.length && mergeChildren(n.children, parentPath, children)) {
      return true
    }
  }
  return false
}

interface State {
  sources: GitSource[]
  trees: Record<string, PageNode[]>
  sshKeys: SshKey[]
  loaded: boolean
  error: string | null
}

export const useSourcesStore = defineStore('sources', {
  state: (): State => ({
    sources: [],
    trees: {},
    sshKeys: [],
    loaded: false,
    error: null,
  }),
  actions: {
    async loadSources(): Promise<void> {
      this.error = null
      try {
        this.sources = await getSources()
        this.loaded = true
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
    async loadTree(id: string): Promise<void> {
      try {
        this.trees[id] = await getSourceTree(id)
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
    async addSource(data: GitSourceCreate): Promise<void> {
      this.error = null
      try {
        const src = await addSource(data)
        this.sources.push(src)
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
        throw e
      }
    },
    async updateSource(id: string, data: GitSourceUpdate): Promise<void> {
      this.error = null
      try {
        const updated = await updateSource(id, data)
        const idx = this.sources.findIndex((s) => s.id === id)
        if (idx !== -1) this.sources[idx] = updated
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
        throw e
      }
    },
    async removeSource(id: string): Promise<void> {
      this.error = null
      try {
        await deleteSource(id)
        this.sources = this.sources.filter((s) => s.id !== id)
        delete this.trees[id]
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
    async syncSource(id: string): Promise<void> {
      this.error = null
      try {
        const updated = await triggerSync(id)
        const idx = this.sources.findIndex((s) => s.id === id)
        if (idx !== -1) this.sources[idx] = updated
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
    async loadSshKeys(): Promise<void> {
      try {
        this.sshKeys = await getSshKeys()
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
    async addSshKey(data: SshKeyCreate): Promise<void> {
      this.error = null
      try {
        const key = await addSshKey(data)
        this.sshKeys.push(key)
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
        throw e
      }
    },
    async removeSshKey(id: string): Promise<void> {
      this.error = null
      try {
        await deleteSshKey(id)
        this.sshKeys = this.sshKeys.filter((k) => k.id !== id)
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
    async loadTreeChildren(sourceId: string, parentPath: string): Promise<void> {
      try {
        const children = await getSourceChildren(sourceId, parentPath)
        const tree = this.trees[sourceId]
        if (tree) {
          mergeChildren(tree, parentPath, children)
          this.trees[sourceId] = [...tree]
        }
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
  },
})
