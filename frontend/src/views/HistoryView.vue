<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { getPageHistory } from '@/api/client'
  import type { HistoryEntry } from '@/api/types'

  const route = useRoute()
  const entries = ref<HistoryEntry[] | null>(null)
  const error = ref<string | null>(null)

  const path = computed(() => {
    const raw = route.params.path
    if (Array.isArray(raw)) return raw.join('/')
    return String(raw ?? 'index')
  })

  async function load(): Promise<void> {
    entries.value = null
    error.value = null
    try {
      entries.value = await getPageHistory(path.value)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  watch(path, load, { immediate: true })

  function timeAgo(ts: string): string {
    const then = new Date(ts).getTime()
    const now = Date.now()
    const diff = Math.max(0, now - then)
    const sec = Math.floor(diff / 1000)
    if (sec < 60) return `${sec}s ago`
    const min = Math.floor(sec / 60)
    if (min < 60) return `${min}m ago`
    const hrs = Math.floor(min / 60)
    if (hrs < 24) return `${hrs}h ago`
    const days = Math.floor(hrs / 24)
    if (days < 30) return `${days}d ago`
    const months = Math.floor(days / 30)
    if (months < 12) return `${months}mo ago`
    return `${Math.floor(months / 12)}y ago`
  }
</script>

<template>
  <article class="mx-auto max-w-3xl px-8 py-6">
    <header class="mb-6">
      <RouterLink :to="`/w/${path}`" class="text-sm text-blue-600 hover:underline">
        &larr; Back to {{ path }}
      </RouterLink>
      <h1 class="text-2xl font-bold mt-2">Page history</h1>
      <p class="text-sm text-slate-500">{{ path }}</p>
    </header>

    <p v-if="error" class="text-red-600">{{ error }}</p>

    <p v-else-if="entries === null" class="text-slate-400">Loading&hellip;</p>

    <p v-else-if="entries.length === 0" class="text-slate-400">
      No history available. Save the page to create the first entry.
    </p>

    <ul v-else class="border border-slate-200 rounded-lg divide-y divide-slate-200">
      <li v-for="entry in entries" :key="entry.sha" class="px-4 py-3 flex gap-4 items-baseline">
        <code class="text-xs text-slate-500 font-mono shrink-0 w-16">{{ entry.sha }}</code>
        <span class="flex-1 min-w-0 truncate">{{ entry.message }}</span>
        <span class="text-xs text-slate-400 shrink-0 hidden sm:inline">{{ entry.author }}</span>
        <span class="text-xs text-slate-400 shrink-0 w-16 text-right">{{
          timeAgo(entry.timestamp)
        }}</span>
      </li>
    </ul>
  </article>
</template>
