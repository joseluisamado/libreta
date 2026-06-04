<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import Breadcrumbs from '@/components/Breadcrumbs.vue'
  import PageToolbar from '@/components/PageToolbar.vue'
  import { useReadingWidth } from '@/composables/usePrefs'
  import { sanitizeHtmlFile } from '@/lib/html'
  import hljs from 'highlight.js'
  import 'highlight.js/styles/github.css'

  // Viewer for HTML *files* in a repo. Renders them with JS stripped (R6 —
  // no user-supplied JS executes), with a toggle to the raw source. Relative
  // asset references (CSS, images, a co-located sidecar folder) are rerooted
  // to the source's /assets endpoint so the page's artifacts load.

  const { width } = useReadingWidth()
  const route = useRoute()

  const path = computed(() => {
    const raw = route.params.path
    if (Array.isArray(raw)) return raw.join('/')
    return String(raw ?? '')
  })

  const sourceId = computed(() => {
    const raw = route.params.sourceId
    return Array.isArray(raw) ? raw[0] : (raw ?? '')
  })

  const watchedLabel = computed(() => {
    const raw = route.params.label
    return Array.isArray(raw) ? raw[0] : (raw ?? '')
  })

  const assetUrl = computed(() => {
    const segments = path.value.split('/').map(encodeURIComponent).join('/')
    if (watchedLabel.value) {
      return `/api/v1/watch/${encodeURIComponent(watchedLabel.value)}/assets/${segments}`
    }
    if (sourceId.value) {
      return `/api/v1/sources/${encodeURIComponent(sourceId.value)}/assets/${segments}`
    }
    return `/api/v1/assets/pages/${segments}`
  })

  const title = computed(() => {
    const parts = path.value.split('/')
    return parts[parts.length - 1] ?? path.value
  })

  const error = ref<string | null>(null)
  const loading = ref(true)
  const rawContent = ref('')

  // 'rendered' shows the sanitized page; 'source' shows highlighted markup.
  const mode = ref<'rendered' | 'source'>('rendered')

  const sanitizedHtml = computed(() =>
    sanitizeHtmlFile(rawContent.value, {
      pagePath: path.value,
      sourceId: sourceId.value || undefined,
      watchedLabel: watchedLabel.value || undefined,
    }),
  )

  const highlightedSource = computed(() => {
    if (!rawContent.value) return ''
    return hljs.highlight(rawContent.value, { language: 'xml' }).value
  })

  async function load(): Promise<void> {
    error.value = null
    loading.value = true
    rawContent.value = ''
    try {
      const r = await fetch(assetUrl.value)
      if (!r.ok) {
        const detail = (await r.json().catch(() => ({}))) as { detail?: string }
        throw new Error(detail.detail ?? `HTTP ${r.status}`)
      }
      rawContent.value = await r.text()
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  watch([path, sourceId, watchedLabel], load, { immediate: true })
</script>

<template>
  <PageToolbar />
  <!-- Rendered/source toggle as a fixed icon button, consistent with the
       markdown viewer (SourcePageView) and clear of the top-right toolbar. -->
  <button
    type="button"
    class="fixed top-3 right-[68px] z-20 bg-white/90 backdrop-blur border border-slate-200 rounded-md p-2 hover:bg-slate-50 shadow-sm"
    :title="mode === 'rendered' ? 'View HTML source' : 'View rendered page'"
    :aria-label="mode === 'rendered' ? 'View HTML source' : 'View rendered page'"
    @click="mode = mode === 'rendered' ? 'source' : 'rendered'"
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
  <a
    :href="assetUrl"
    download
    class="fixed top-3 right-[112px] z-20 bg-white/90 backdrop-blur border border-slate-200 rounded-md p-2 hover:bg-slate-50 shadow-sm"
    title="Download file"
    aria-label="Download file"
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
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  </a>

  <article class="mx-auto py-6" :class="width === 'wide' ? 'max-w-none px-12' : 'max-w-4xl px-8'">
    <header class="flex items-center justify-between mb-4">
      <Breadcrumbs
        :path="path"
        :source-id="sourceId || undefined"
        :watched-label="watchedLabel || undefined"
      />
    </header>
    <h1 class="text-xl font-mono font-bold mb-1 text-slate-800">{{ title }}</h1>
    <p class="text-xs text-slate-400 mb-4">HTML · scripts removed for safe rendering</p>

    <p v-if="error" class="text-red-600">Failed to load file: {{ error }}</p>
    <p v-else-if="loading" class="text-slate-400">Loading…</p>

    <!-- Rendered in a sandboxed iframe (sandbox="", i.e. no allow-scripts and
         no allow-same-origin): the page's own CSS is isolated to the iframe
         document so it can't leak into Libreta's chrome, and no JS executes
         (R6). Content is still sanitized first as defense-in-depth. The frame
         scrolls internally; we can't measure its height (cross-origin), so it
         fills the viewport below the header. -->
    <iframe
      v-else-if="mode === 'rendered'"
      :srcdoc="sanitizedHtml"
      sandbox=""
      referrerpolicy="no-referrer"
      title="Rendered HTML"
      class="w-full bg-white rounded-md border border-slate-200 h-[calc(100vh-9rem)]"
    />

    <!-- Source -->
    <pre
      v-else
      class="bg-white rounded-md border border-slate-200 overflow-auto p-4 text-sm"
    ><code class="hljs language-xml" v-html="highlightedSource" /></pre>
  </article>
</template>
