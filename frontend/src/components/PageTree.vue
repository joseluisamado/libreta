<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import type { PageNode } from '@/api/types'

  defineProps<{ nodes: PageNode[] }>()

  // Per-folder open/closed state, keyed by node.path. Persisted to localStorage
  // so the tree feels stable across page navigations.
  const STORAGE_KEY = 'libreta:tree-open'

  function loadState(): Record<string, boolean> {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY)
      if (!raw) return {}
      const parsed = JSON.parse(raw) as Record<string, boolean>
      return typeof parsed === 'object' && parsed ? parsed : {}
    } catch {
      return {}
    }
  }

  const openState = ref<Record<string, boolean>>(loadState())

  watch(
    openState,
    (s) => {
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(s))
      } catch {
        /* ignore quota / private mode */
      }
    },
    { deep: true },
  )

  // Default behavior: a folder is open unless explicitly closed.
  function isOpen(path: string): boolean {
    return openState.value[path] !== false
  }

  function toggle(path: string): void {
    openState.value = { ...openState.value, [path]: !isOpen(path) }
  }
</script>

<template>
  <ul class="text-sm">
    <li v-for="node in nodes" :key="node.path" class="my-0.5">
      <div class="flex items-start gap-1">
        <button
          v-if="node.children.length"
          type="button"
          class="shrink-0 w-4 h-4 mt-0.5 flex items-center justify-center text-slate-400 hover:text-slate-700"
          :aria-expanded="isOpen(node.path)"
          :aria-label="isOpen(node.path) ? 'Collapse folder' : 'Expand folder'"
          @click="toggle(node.path)"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class="w-3 h-3 transition-transform"
            :class="{ 'rotate-90': isOpen(node.path) }"
            viewBox="0 0 12 12"
            fill="currentColor"
          >
            <path d="M4 2 L8 6 L4 10 Z" />
          </svg>
        </button>
        <span v-else class="shrink-0 w-4 h-4" aria-hidden="true" />
        <RouterLink
          :to="`/w/${node.path}`"
          class="flex-1 truncate"
          :class="
            node.children.length
              ? 'text-slate-800 font-medium hover:text-blue-600'
              : 'text-slate-700 hover:text-blue-600'
          "
          active-class="text-blue-700 font-semibold"
        >
          {{ node.title }}
        </RouterLink>
      </div>
      <PageTree
        v-if="node.children.length && isOpen(node.path)"
        :nodes="node.children"
        class="ml-3 border-l border-slate-200 pl-2"
      />
    </li>
  </ul>
</template>
