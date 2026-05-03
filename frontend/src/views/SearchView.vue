<script setup lang="ts">
  import { ref, watch, computed, onMounted, nextTick } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { searchPages } from '@/api/client'
  import type { SearchResult } from '@/api/types'

  const route = useRoute()
  const router = useRouter()

  const q = ref((route.query.q as string) ?? '')
  const results = ref<SearchResult[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const activeIndex = ref(-1)
  const inputRef = ref<HTMLInputElement | null>(null)

  async function doSearch(query: string): Promise<void> {
    const trimmed = query.trim()
    if (!trimmed) {
      results.value = []
      return
    }
    loading.value = true
    error.value = null
    activeIndex.value = -1
    try {
      results.value = await searchPages(trimmed)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      results.value = []
    } finally {
      loading.value = false
    }
  }

  // Sync URL ↔ query
  watch(q, (val) => {
    router.replace({ path: '/search', query: val.trim() ? { q: val.trim() } : {} })
  })

  watch(
    () => route.query.q as string | undefined,
    (val) => {
      const v = val ?? ''
      if (v !== q.value) q.value = v
    },
  )

  // Debounced search
  let debounceTimer: ReturnType<typeof setTimeout> | undefined
  watch(q, (val) => {
    clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => void doSearch(val), 250)
  })

  onMounted(() => {
    inputRef.value?.focus()
    if (q.value) void doSearch(q.value)
  })

  const hasResults = computed(() => results.value.length > 0)

  function navigate(delta: number): void {
    if (!hasResults.value) return
    activeIndex.value = Math.max(-1, Math.min(results.value.length - 1, activeIndex.value + delta))
    nextTick(() => {
      const el = document.querySelector<HTMLElement>(`[data-result-index="${activeIndex.value}"]`)
      el?.scrollIntoView({ block: 'nearest' })
    })
  }

  function selectActive(): void {
    const result = results.value[activeIndex.value]
    if (activeIndex.value >= 0 && result) {
      void router.push(`/w/${result.path}`)
    }
  }

  function onKeydown(e: KeyboardEvent): void {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      navigate(1)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      navigate(-1)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      selectActive()
    } else if (e.key === 'Escape') {
      q.value = ''
      results.value = []
      activeIndex.value = -1
    }
  }
</script>

<template>
  <div class="max-w-2xl mx-auto px-6 py-8">
    <h1 class="text-2xl font-semibold mb-6 text-slate-800">Search</h1>

    <!-- Search input -->
    <div class="relative mb-6">
      <svg
        class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none"
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
      <input
        ref="inputRef"
        v-model="q"
        type="search"
        placeholder="Search pages… (↑↓ to navigate, Enter to open)"
        class="w-full pl-10 pr-4 py-2.5 rounded-lg border border-slate-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        autocomplete="off"
        @keydown="onKeydown"
      />
    </div>

    <!-- Loading -->
    <p v-if="loading" class="text-sm text-slate-400">Searching…</p>

    <!-- Error -->
    <p v-else-if="error" class="text-sm text-red-600">{{ error }}</p>

    <!-- Empty -->
    <p v-else-if="q.trim() && !loading && !hasResults" class="text-sm text-slate-500">
      No results for <strong>{{ q.trim() }}</strong
      >.
    </p>

    <!-- Results -->
    <ul v-else-if="hasResults" class="space-y-2">
      <li
        v-for="(result, i) in results"
        :key="result.path"
        :data-result-index="i"
        :class="[
          'rounded-lg border px-4 py-3 cursor-pointer transition-colors',
          i === activeIndex
            ? 'border-blue-400 bg-blue-50'
            : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50',
        ]"
        @click="() => $router.push(`/w/${result.path}`)"
        @mouseenter="activeIndex = i"
      >
        <div class="flex items-baseline justify-between gap-2 mb-1">
          <RouterLink
            :to="`/w/${result.path}`"
            class="font-medium text-blue-700 hover:underline text-sm"
          >
            {{ result.title || result.path }}
          </RouterLink>
          <span class="text-xs text-slate-400 shrink-0">{{ result.path }}</span>
        </div>
        <!-- eslint-disable-next-line vue/no-v-html -->
        <p class="text-xs text-slate-600 leading-relaxed" v-html="result.snippet" />
        <div v-if="result.tags" class="mt-1.5 flex flex-wrap gap-1">
          <span
            v-for="tag in result.tags.split(' ').filter(Boolean)"
            :key="tag"
            class="px-1.5 py-0.5 rounded text-xs bg-slate-100 text-slate-500"
          >
            {{ tag }}
          </span>
        </div>
      </li>
    </ul>

    <!-- Idle state -->
    <p v-else class="text-sm text-slate-400">
      Type to search. Use <code class="bg-slate-100 px-1 rounded">tag:name</code> to filter by tag.
    </p>
  </div>
</template>

<style scoped>
  :deep(mark) {
    background-color: #fef08a;
    border-radius: 2px;
    padding: 0 1px;
  }
</style>
