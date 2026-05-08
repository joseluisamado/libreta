<script setup lang="ts">
  import { computed } from 'vue'
  import type { PendingCommit } from '@/api/types'

  const props = defineProps<{
    sourceId: string
    commits: PendingCommit[]
    loading: boolean
    error: string | null
  }>()

  defineEmits<{ close: [] }>()

  // Aggregate the changed pages across all pending commits, with the most
  // recent commit-time first. The user wanted "list of changed pages," so
  // the page is the unit; the underlying commits are listed underneath
  // each row for context.
  interface PageEntry {
    path: string
    commits: PendingCommit[]
  }

  const pages = computed<PageEntry[]>(() => {
    const byPath = new Map<string, PendingCommit[]>()
    for (const c of props.commits) {
      for (const p of c.paths) {
        const list = byPath.get(p) ?? []
        list.push(c)
        byPath.set(p, list)
      }
    }
    const out: PageEntry[] = []
    for (const [path, commits] of byPath.entries()) {
      out.push({ path, commits })
    }
    // Sort by most-recent commit timestamp on each page, descending.
    out.sort((a, b) => {
      const ta = Math.max(...a.commits.map((c) => Date.parse(c.timestamp)))
      const tb = Math.max(...b.commits.map((c) => Date.parse(c.timestamp)))
      return tb - ta
    })
    return out
  })

  function relTime(iso: string): string {
    const d = Date.parse(iso)
    const diff = (Date.now() - d) / 1000
    if (diff < 60) return 'just now'
    if (diff < 3600) return `${Math.round(diff / 60)}m ago`
    if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
    return new Date(d).toLocaleDateString()
  }
</script>

<template>
  <div
    class="ml-3 mt-1 mb-1 rounded border border-amber-200 bg-amber-50 text-xs"
    role="dialog"
    aria-label="Pending local changes"
  >
    <div class="flex items-center justify-between border-b border-amber-200 px-2 py-1">
      <span class="font-medium text-amber-800">Unpushed changes</span>
      <button
        type="button"
        class="text-amber-700 hover:text-amber-900"
        title="Close"
        @click="$emit('close')"
      >
        ✕
      </button>
    </div>

    <div v-if="loading" class="px-2 py-2 text-amber-700">Loading…</div>

    <div v-else-if="error" class="px-2 py-2 text-red-700">{{ error }}</div>

    <div v-else-if="pages.length === 0" class="px-2 py-2 text-slate-500">
      No page-level changes (only assets / metadata pending).
    </div>

    <ul v-else class="divide-y divide-amber-200">
      <li v-for="entry in pages" :key="entry.path" class="px-2 py-1.5">
        <RouterLink
          :to="`/source/${sourceId}/${entry.path}`"
          class="font-medium text-blue-700 hover:underline break-all"
        >
          {{ entry.path }}
        </RouterLink>
        <ul class="mt-0.5 ml-2 text-[11px] text-slate-600 space-y-0.5">
          <li
            v-for="c in entry.commits"
            :key="c.sha"
            class="flex gap-1.5 items-baseline"
            :title="`${c.author} — ${c.message}`"
          >
            <span class="font-mono text-slate-400">{{ c.sha }}</span>
            <span class="truncate">{{ c.message }}</span>
            <span class="ml-auto whitespace-nowrap text-slate-400">{{ relTime(c.timestamp) }}</span>
          </li>
        </ul>
      </li>
    </ul>
  </div>
</template>
