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
  updateSshKey,
  deleteSshKey,
  getGiteaServers,
  addGiteaServer,
  updateGiteaServer,
  deleteGiteaServer,
  discoverGiteaRepos,
  importGiteaRepos,
} from '@/api/client'
import type {
  GiteaRepo,
  GiteaServer,
  GiteaServerCreate,
  GiteaServerUpdate,
  GitSource,
  GitSourceCreate,
  GitSourceUpdate,
  OtherFile,
  PageNode,
  SshKey,
  SshKeyCreate,
} from '@/api/types'

function mergeChildren(
  nodes: PageNode[],
  parentPath: string,
  children: PageNode[],
  otherFiles: OtherFile[],
): boolean {
  for (const n of nodes) {
    if (n.path === parentPath) {
      n.children = children
      n.has_more = false
      n.other_files = otherFiles
      return true
    }
    if (n.children?.length && mergeChildren(n.children, parentPath, children, otherFiles)) {
      return true
    }
  }
  return false
}

interface State {
  sources: GitSource[]
  trees: Record<string, PageNode[]>
  sshKeys: SshKey[]
  giteaServers: GiteaServer[]
  loaded: boolean
  error: string | null
}

export const useSourcesStore = defineStore('sources', {
  state: (): State => ({
    sources: [],
    trees: {},
    sshKeys: [],
    giteaServers: [],
    loaded: false,
    error: null,
  }),
  actions: {
    async loadSources(): Promise<void> {
      this.error = null
      try {
        const fresh = await getSources()
        // Always assign a brand-new array so Vue treats the reference as
        // changed even if the new payload happens to be deep-equal to the
        // current one (e.g. only the pending_count field flipped).
        this.sources = fresh.map((s) => ({ ...s }))
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
    async updateSshKey(id: string, label: string): Promise<void> {
      this.error = null
      try {
        const updated = await updateSshKey(id, { label })
        const idx = this.sshKeys.findIndex((k) => k.id === id)
        if (idx !== -1) this.sshKeys[idx] = updated
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
    async loadGiteaServers(): Promise<void> {
      try {
        this.giteaServers = await getGiteaServers()
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
    async addGiteaServer(data: GiteaServerCreate): Promise<void> {
      this.error = null
      try {
        const server = await addGiteaServer(data)
        this.giteaServers.push(server)
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
        throw e
      }
    },
    async updateGiteaServer(id: string, data: GiteaServerUpdate): Promise<void> {
      this.error = null
      try {
        const updated = await updateGiteaServer(id, data)
        const idx = this.giteaServers.findIndex((s) => s.id === id)
        if (idx !== -1) this.giteaServers[idx] = updated
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
        throw e
      }
    },
    async removeGiteaServer(id: string): Promise<void> {
      this.error = null
      try {
        await deleteGiteaServer(id)
        this.giteaServers = this.giteaServers.filter((s) => s.id !== id)
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
    // Discover returns the repo list to the caller (the Admin view) rather
    // than storing it: it is a transient picker, not durable store state.
    async discoverGiteaRepos(serverId: string, owner: string): Promise<GiteaRepo[]> {
      this.error = null
      try {
        return await discoverGiteaRepos(serverId, owner)
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
        throw e
      }
    },
    async importGiteaRepos(serverId: string, owner: string, repos: string[]): Promise<GitSource[]> {
      this.error = null
      try {
        const created = await importGiteaRepos(serverId, { owner, repos })
        // Newly imported sources clone in the background; surface them now.
        for (const src of created) this.sources.push(src)
        return created
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
        throw e
      }
    },
    async loadTreeChildren(sourceId: string, parentPath: string): Promise<void> {
      try {
        const result = await getSourceChildren(sourceId, parentPath)
        const tree = this.trees[sourceId]
        if (tree) {
          mergeChildren(tree, parentPath, result.children, result.other_files)
          this.trees[sourceId] = [...tree]
        }
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
    // Walk down each ancestor of *path*, fetching children for any segment
    // not already present in the tree. Needed when navigating directly to a
    // URL deeper than the initial tree depth (the intermediate folders are
    // unknown to the client and would never be expanded otherwise).
    async ensurePathExpanded(sourceId: string, path: string): Promise<void> {
      if (!path) return
      const segments = path.split('/').filter(Boolean)
      let acc = ''
      for (const seg of segments) {
        acc = acc ? `${acc}/${seg}` : seg
        await this.loadTreeChildren(sourceId, acc)
      }
    },
  },
})
