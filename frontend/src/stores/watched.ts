import { defineStore } from 'pinia'
import {
  getWatchedFolders,
  addWatchedFolder,
  updateWatchedFolder,
  removeWatchedFolder,
  reorderWatchedFolders,
  getWatchedTree,
  getWatchedChildren,
} from '@/api/client'
import type { PageNode, WatchedFolder } from '@/api/types'
import { isPathLoaded, mergeChildren, mergeReloadedTree } from '@/utils/pageTree'

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
        const fresh = await getWatchedTree(label)
        // Preserve folders the user had expanded past the tree's depth limit;
        // see mergeReloadedTree.
        this.trees[label] = mergeReloadedTree(fresh, this.trees[label])
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
    async reorderFolders(orderedLabels: string[]): Promise<void> {
      this.error = null
      const prev = this.folders
      const byLabel = new Map(prev.map((f) => [f.label, f]))
      this.folders = orderedLabels.map((l) => byLabel.get(l)).filter((f): f is WatchedFolder => !!f)
      try {
        await reorderWatchedFolders(orderedLabels)
      } catch (e) {
        this.folders = prev
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
        const tree = this.trees[label]
        if (tree && isPathLoaded(tree, acc)) continue
        await this.loadTreeChildren(label, acc)
      }
    },
  },
})
