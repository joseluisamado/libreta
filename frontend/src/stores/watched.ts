import { defineStore } from 'pinia'
import {
  getWatchedFolders,
  addWatchedFolder,
  removeWatchedFolder,
  getWatchedTree,
} from '@/api/client'
import type { PageNode, WatchedFolder } from '@/api/types'

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
  },
})
