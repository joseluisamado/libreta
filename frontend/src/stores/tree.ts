import { defineStore } from 'pinia'
import { getTree } from '@/api/client'
import type { PageNode } from '@/api/types'

interface State {
  nodes: PageNode[]
  loaded: boolean
  error: string | null
}

export const useTreeStore = defineStore('tree', {
  state: (): State => ({ nodes: [], loaded: false, error: null }),
  actions: {
    async load(): Promise<void> {
      try {
        this.nodes = await getTree()
        this.loaded = true
        this.error = null
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      }
    },
  },
})
