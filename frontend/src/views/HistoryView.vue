<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { getPageHistory } from '@/api/client'
  import type { HistoryEntry } from '@/api/types'

  const route = useRoute()
  const router = useRouter()
  const entries = ref<HistoryEntry[] | null>(null)
  const error = ref<string | null>(null)
  const selA = ref<string | null>(null)
  const selB = ref<string | null>(null)

  const path = computed(() => {
    const raw = route.params.path
    if (Array.isArray(raw)) return raw.join('/')
    return String(raw ?? 'index')
  })

  async function load(): Promise<void> {
    entries.value = null
    error.value = null
    selA.value = null
    selB.value = null
    try {
      const loaded = await getPageHistory(path.value)
      entries.value = loaded
      // Pre-select the two newest commits when there are at least two.
      if (loaded.length >= 2) {
        selB.value = loaded[0]!.sha
        selA.value = loaded[1]!.sha
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  watch(path, load, { immediate: true })

  const canCompare = computed(() => !!selA.value && !!selB.value && selA.value !== selB.value)

  function compare(): void {
    if (!canCompare.value) return
    router.push({
      path: `/diff/${path.value}`,
      query: { a: selA.value!, b: selB.value! },
    })
  }

  function diffWithPrevious(idx: number): void {
    const list = entries.value
    if (!list || idx >= list.length - 1) return
    const newer = list[idx]!.sha
    const older = list[idx + 1]!.sha
    router.push({ path: `/diff/${path.value}`, query: { a: older, b: newer } })
  }

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

    <template v-else>
      <div
        v-if="entries.length >= 2"
        class="mb-3 flex items-center justify-between text-xs text-slate-500"
      >
        <span>Pick two revisions and click Compare, or use “diff vs previous” on any row.</span>
        <button
          type="button"
          class="px-3 py-1 rounded border text-xs cursor-pointer transition-colors"
          :class="
            canCompare
              ? 'border-blue-300 text-blue-700 hover:bg-blue-50'
              : 'border-slate-200 text-slate-400 cursor-not-allowed'
          "
          :disabled="!canCompare"
          @click="compare"
        >
          Compare A &rarr; B
        </button>
      </div>

      <ul class="border border-slate-200 rounded-lg divide-y divide-slate-200">
        <li
          v-for="(entry, idx) in entries"
          :key="entry.sha"
          class="px-4 py-3 flex gap-3 items-baseline group"
        >
          <label
            class="shrink-0 flex items-center gap-1 text-xs text-slate-400 cursor-pointer"
            title="Older revision (A)"
          >
            <input
              type="radio"
              name="diff-a"
              :value="entry.sha"
              v-model="selA"
              class="cursor-pointer"
            />
            A
          </label>
          <label
            class="shrink-0 flex items-center gap-1 text-xs text-slate-400 cursor-pointer"
            title="Newer revision (B)"
          >
            <input
              type="radio"
              name="diff-b"
              :value="entry.sha"
              v-model="selB"
              class="cursor-pointer"
            />
            B
          </label>
          <code class="text-xs text-slate-500 font-mono shrink-0 w-16">{{ entry.sha }}</code>
          <span class="flex-1 min-w-0 truncate">{{ entry.message }}</span>
          <button
            v-if="idx < entries.length - 1"
            type="button"
            class="shrink-0 opacity-0 group-hover:opacity-100 text-xs text-blue-600 hover:underline cursor-pointer transition-opacity"
            title="Diff against previous revision"
            @click="diffWithPrevious(idx)"
          >
            diff vs prev
          </button>
          <span class="text-xs text-slate-400 shrink-0 hidden sm:inline">{{ entry.author }}</span>
          <span class="text-xs text-slate-400 shrink-0 w-16 text-right">{{
            timeAgo(entry.timestamp)
          }}</span>
        </li>
      </ul>
    </template>
  </article>
</template>
