<script setup lang="ts">
  import { ref, computed, onMounted } from 'vue'
  import { useRouter } from 'vue-router'
  import { useSourcesStore } from '@/stores/sources'
  import type { PageNode } from '@/api/types'
  import logoUrl from '@/assets/logo.svg'

  const router = useRouter()
  const sources = useSourcesStore()

  // ── Search ────────────────────────────────────────────────────────────

  const searchQuery = ref('')

  function doSearch(): void {
    const q = searchQuery.value.trim()
    if (q) {
      router.push({ path: '/search', query: { q } })
    } else {
      router.push('/search')
    }
  }

  // ── Stats (aggregated across all git sources) ─────────────────────────

  function countPages(nodes: PageNode[]): number {
    let n = 0
    for (const node of nodes) {
      if (!node.is_directory) n++
      if (node.children.length) n += countPages(node.children)
    }
    return n
  }

  function countNamespaces(nodes: PageNode[]): number {
    let n = 0
    for (const node of nodes) {
      if (node.is_directory) n++
      if (node.children.length) n += countNamespaces(node.children)
    }
    return n
  }

  const pageCount = computed(() => {
    let n = 0
    for (const tree of Object.values(sources.trees)) {
      n += countPages(tree)
    }
    return n
  })

  const namespaceCount = computed(() => {
    let n = 0
    for (const tree of Object.values(sources.trees)) {
      n += countNamespaces(tree)
    }
    return n
  })

  const sourceCount = computed(() => sources.sources.length)

  // ── Load ──────────────────────────────────────────────────────────────

  onMounted(async () => {
    if (!sources.loaded) await sources.loadSources()
    for (const src of sources.sources) {
      if (!sources.trees[src.id]) {
        await sources.loadTree(src.id)
      }
    }
  })
</script>

<template>
  <div class="max-w-3xl mx-auto px-6 py-12 md:py-20">
    <!-- ── Hero ─────────────────────────────────────────────────────── -->
    <div class="text-center mb-12">
      <img :src="logoUrl" alt="" class="w-16 h-16 mx-auto mb-4" />
      <h1 class="text-3xl font-bold text-slate-800 mb-3">Libreta</h1>
      <p class="text-slate-500 mb-8">Your wiki, backed by a git repository of markdown files.</p>

      <form @submit.prevent="doSearch" class="max-w-lg mx-auto">
        <div class="flex gap-2">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search pages..."
            class="flex-1 px-4 py-3 rounded-lg border border-slate-300 bg-white text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent"
          />
          <button
            type="submit"
            class="px-5 py-3 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            Search
          </button>
        </div>
      </form>
    </div>

    <!-- ── Stats cards ──────────────────────────────────────────────── -->
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-12">
      <div class="rounded-lg border border-slate-200 bg-white p-5 text-center">
        <p class="text-3xl font-bold text-blue-600">{{ pageCount }}</p>
        <p class="text-sm text-slate-500">pages</p>
      </div>
      <div class="rounded-lg border border-slate-200 bg-white p-5 text-center">
        <p class="text-3xl font-bold text-blue-600">{{ namespaceCount }}</p>
        <p class="text-sm text-slate-500">folders</p>
      </div>
      <div class="rounded-lg border border-slate-200 bg-white p-5 text-center">
        <p class="text-3xl font-bold text-blue-600">{{ sourceCount }}</p>
        <p class="text-sm text-slate-500">repos</p>
      </div>
    </div>
  </div>
</template>
