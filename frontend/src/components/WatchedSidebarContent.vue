<script setup lang="ts">
  import { ref, watch } from 'vue'
  import { useWatchedStore } from '@/stores/watched'
  import PageTree from '@/components/PageTree.vue'
  import type { PageNode } from '@/api/types'

  const store = useWatchedStore()
  const loadingPaths = ref<Set<string>>(new Set())

  // ----- Persisted expand/collapse state --------------------------------------

  const STORAGE_KEY = 'libreta:watched-open'

  function loadExpanded(): Record<string, boolean> {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY)
      if (!raw) return {}
      const parsed = JSON.parse(raw) as Record<string, boolean>
      return typeof parsed === 'object' && parsed ? parsed : {}
    } catch {
      return {}
    }
  }

  const expanded = ref<Record<string, boolean>>(loadExpanded())

  watch(
    expanded,
    (s) => {
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(s))
      } catch {
        /* ignore quota / private mode */
      }
    },
    { deep: true },
  )

  store.loadFolders()

  // Reload tree data for any folder that was expanded in a previous session
  for (const label of Object.keys(expanded.value)) {
    if (expanded.value[label]) {
      store.loadTree(label)
    }
  }

  function toggleExpand(label: string): void {
    if (expanded.value[label]) {
      expanded.value = { ...expanded.value, [label]: false }
    } else {
      expanded.value = { ...expanded.value, [label]: true }
      store.loadTree(label)
    }
  }

  async function handleExpand(label: string, node: PageNode): Promise<void> {
    loadingPaths.value = new Set([...loadingPaths.value, node.path])
    try {
      await store.loadTreeChildren(label, node.path)
    } finally {
      const next = new Set(loadingPaths.value)
      next.delete(node.path)
      loadingPaths.value = next
    }
  }
</script>

<template>
  <div class="text-sm">
    <p v-if="store.error" class="text-red-600 mb-2">{{ store.error }}</p>

    <ul v-if="store.folders.length" class="mb-3">
      <li v-for="f in store.folders" :key="f.label" class="mb-1">
        <div class="flex items-start gap-1">
          <button
            type="button"
            class="shrink-0 w-4 h-4 mt-0.5 flex items-center justify-center text-slate-400 hover:text-slate-700"
            :aria-expanded="!!expanded[f.label]"
            :aria-label="expanded[f.label] ? 'Collapse folder' : 'Expand folder'"
            @click="toggleExpand(f.label)"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              class="w-3 h-3 transition-transform"
              :class="{ 'rotate-90': expanded[f.label] }"
              viewBox="0 0 12 12"
              fill="currentColor"
            >
              <path d="M4 2 L8 6 L4 10 Z" />
            </svg>
          </button>
          <button
            type="button"
            class="flex-1 min-w-0 truncate text-left text-sm font-medium text-slate-700 hover:text-blue-600"
            @click="toggleExpand(f.label)"
          >
            {{ f.label }}
          </button>
        </div>
        <p class="text-[11px] text-slate-400 ml-5 truncate" :title="f.path">
          {{ f.path }}
        </p>
        <PageTree
          v-if="expanded[f.label] && store.trees[f.label]"
          :nodes="store.trees[f.label]!"
          :link-prefix="'/watch/' + f.label"
          :storage-key="'libreta:tree-watch-' + f.label"
          :on-expand="(node: PageNode) => handleExpand(f.label, node)"
          :loading-paths="loadingPaths"
          :default-open-depth="1"
          class="ml-3 border-l-2 border-slate-200 pl-2 mt-0.5"
        />
      </li>
    </ul>

    <p v-if="store.loaded && !store.folders.length" class="text-slate-400 text-xs">
      No watched folders.
    </p>
  </div>
</template>
