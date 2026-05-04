<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { getWatchedPage } from '@/api/client'
  import type { PageRead } from '@/api/types'
  import { renderMarkdown } from '@/markdown'
  import { useReadingWidth } from '@/composables/usePrefs'
  import { useViewMode } from '@/composables/useViewMode'
  import Breadcrumbs from '@/components/Breadcrumbs.vue'
  import PageToolbar from '@/components/PageToolbar.vue'
  import PageToc from '@/components/PageToc.vue'
  import hljs from 'highlight.js'
  import 'highlight.js/styles/github.css'

  const { width } = useReadingWidth()
  const { mode, toggle: toggleViewMode } = useViewMode()

  const route = useRoute()
  const page = ref<PageRead | null>(null)
  const error = ref<string | null>(null)

  const label = computed(() => String(route.params.label))
  const path = computed(() => {
    const raw = route.params.path
    if (Array.isArray(raw)) return raw.join('/')
    return String(raw ?? '')
  })

  async function load(): Promise<void> {
    page.value = null
    error.value = null
    try {
      page.value = await getWatchedPage(label.value, path.value)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  watch([label, path], load, { immediate: true })

  const bodyHasMatchingH1 = computed(() => {
    if (!page.value) return false
    const firstLine = page.value.body.trimStart().split('\n', 1)[0] ?? ''
    if (!firstLine.startsWith('# ')) return false
    return firstLine.slice(2).trim() === page.value.meta.title
  })

  const html = computed(() => {
    if (!page.value) return ''
    return renderMarkdown(page.value.body, page.value.path)
  })

  const highlightedSource = computed(() => {
    if (!page.value) return ''
    return hljs.highlight(page.value.body, { language: 'markdown' }).value
  })
</script>

<template>
  <PageToolbar />
  <button
    v-if="page"
    type="button"
    class="fixed top-3 right-[56px] z-20 bg-white/90 backdrop-blur border border-slate-200 rounded-md p-2 hover:bg-slate-50 shadow-sm"
    :title="mode === 'rendered' ? 'View markdown source' : 'View rendered page'"
    :aria-label="mode === 'rendered' ? 'View markdown source' : 'View rendered page'"
    @click="toggleViewMode"
  >
    <svg
      v-if="mode === 'rendered'"
      xmlns="http://www.w3.org/2000/svg"
      class="w-4 h-4 text-slate-600"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
    </svg>
    <svg
      v-else
      xmlns="http://www.w3.org/2000/svg"
      class="w-4 h-4 text-slate-600"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  </button>
  <RouterLink
    v-if="page"
    :to="`/edit-watch/${label}/${page.path}`"
    class="fixed top-3 right-[100px] z-30 bg-white/90 backdrop-blur border border-slate-200 rounded-md p-2 hover:bg-slate-50 shadow-sm"
    title="Edit this page"
    aria-label="Edit this page"
  >
    <svg
      xmlns="http://www.w3.org/2000/svg"
      class="w-4 h-4 text-slate-600"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
    </svg>
  </RouterLink>
  <PageToc v-if="page" :html="html" />
  <article class="mx-auto px-8 py-6" :class="width === 'wide' ? 'max-w-none' : 'max-w-3xl'">
    <p v-if="error" class="text-red-600">{{ error }}</p>
    <template v-else-if="page">
      <header
        class="flex items-center justify-between mb-4"
        :class="width === 'wide' ? 'pr-48' : ''"
      >
        <Breadcrumbs :path="page.path" :watched-label="label" />
      </header>
      <h1 v-if="!bodyHasMatchingH1" class="text-3xl font-bold">{{ page.meta.title }}</h1>
      <div v-if="mode === 'rendered'" class="prose" v-html="html" />
      <pre
        v-else
        class="bg-[#f6f8fa] rounded-md p-6 overflow-auto text-sm leading-relaxed border border-slate-200"
      ><code class="hljs language-markdown" v-html="highlightedSource" /></pre>
      <p v-if="page.meta.tags.length" class="mt-8 text-xs text-slate-500">
        <span v-for="t in page.meta.tags" :key="t" class="mr-2">#{{ t }}</span>
      </p>
    </template>
    <p v-else class="text-slate-400">Loading…</p>
  </article>
</template>
