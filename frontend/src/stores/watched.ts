import { defineStore } from 'pinia'
import {
  getWatchedFolders,
  addWatchedFolder,
  updateWatchedFolder,
  removeWatchedFolder,
  getWatchedTree,
  getWatchedChildren,
} from '@/api/client'
import type { OtherFile, PageNode, WatchedFolder } from '@/api/types'

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
  folders: WatchedFolder[]
  trees: Record<string, PageNode[]>
  loaded: boolean
  error: string | null
}

export const useWatchedStore = defineStore('watched', {
  state: (): State => ({ folders: [], trees: {}, loaded: false, error: null }),
  actions: {
    async loadFolders(): Promise<void> {
      this.error = null
      try {
        this.folders = await getWatchedFolders()
        this.loaded = true
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
    async loadTree(label: string): Promise<void> {
      try {
        this.trees[label] = await getWatchedTree(label)
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
    async addFolder(label: string, path: string): Promise<void> {
      this.error = null
      try {
        await addWatchedFolder({ label, path })
        await this.loadFolders()
        await this.loadTree(label)
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
        throw e
      }
    },
    async updateFolder(label: string, newLabel: string, path: string): Promise<void> {
      this.error = null
      try {
        await updateWatchedFolder(label, { label: newLabel, path })
        // The label may have changed (it's the key), so reload from scratch
        // and drop any cached tree under the old key.
        if (newLabel !== label) delete this.trees[label]
        await this.loadFolders()
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
        throw e
      }
    },
    async removeFolder(label: string): Promise<void> {
      this.error = null
      try {
        await removeWatchedFolder(label)
        this.folders = this.folders.filter((f) => f.label !== label)
        delete this.trees[label]
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
    async loadTreeChildren(label: string, parentPath: string): Promise<void> {
      try {
        const result = await getWatchedChildren(label, parentPath)
        const tree = this.trees[label]
        if (tree) {
          mergeChildren(tree, parentPath, result.children, result.other_files)
          this.trees[label] = [...tree]
        }
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
    async ensurePathExpanded(label: string, path: string): Promise<void> {
      if (!path) return
      const segments = path.split('/').filter(Boolean)
      let acc = ''
      for (const seg of segments) {
        acc = acc ? `${acc}/${seg}` : seg
        await this.loadTreeChildren(label, acc)
      }
    },
  },
})
