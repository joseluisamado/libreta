<script setup lang="ts">
  import { computed, onBeforeUnmount, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import * as pdfjs from 'pdfjs-dist/legacy/build/pdf.mjs'
  import workerUrl from 'pdfjs-dist/legacy/build/pdf.worker.mjs?url'
  import Breadcrumbs from '@/components/Breadcrumbs.vue'
  import PageToolbar from '@/components/PageToolbar.vue'
  import { useReadingWidth } from '@/composables/usePrefs'

  pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

  const route = useRoute()
  const { width } = useReadingWidth()

  const path = computed(() => {
    const raw = route.params.path
    if (Array.isArray(raw)) return raw.join('/')
    return String(raw ?? '')
  })

  const sourceId = computed(() => {
    const raw = route.params.sourceId
    return Array.isArray(raw) ? raw[0] : (raw ?? '')
  })

  const assetUrl = computed(() => {
    const segments = path.value.split('/').map(encodeURIComponent).join('/')
    if (sourceId.value) {
      return `/api/v1/sources/${encodeURIComponent(sourceId.value)}/assets/${segments}`
    }
    return `/api/v1/assets/pages/${segments}`
  })

  const title = computed(() => {
    const last = path.value.split('/').pop() ?? path.value
    return last.replace(/\.pdf$/i, '').replace(/[-_]/g, ' ')
  })

  const error = ref<string | null>(null)
  const loading = ref(true)
  const containerEl = ref<HTMLElement | null>(null)
  let activeDoc: pdfjs.PDFDocumentProxy | null = null
  let renderToken = 0

  async function render(): Promise<void> {
    error.value = null
    loading.value = true
    const myToken = ++renderToken

    if (activeDoc) {
      activeDoc.destroy()
      activeDoc = null
    }
    if (containerEl.value) containerEl.value.innerHTML = ''

    try {
      const doc = await pdfjs.getDocument({ url: assetUrl.value }).promise
      if (myToken !== renderToken) {
        doc.destroy()
        return
      }
      activeDoc = doc

      const container = containerEl.value
      if (!container) return

      // Render width: target the container's content width so pages scale to fit.
      const containerWidth = container.clientWidth || 800
      const dpr = window.devicePixelRatio || 1

      for (let i = 1; i <= doc.numPages; i++) {
        if (myToken !== renderToken) return
        const page = await doc.getPage(i)
        const baseViewport = page.getViewport({ scale: 1 })
        const scale = containerWidth / baseViewport.width
        const viewport = page.getViewport({ scale })

        const canvas = document.createElement('canvas')
        canvas.width = Math.floor(viewport.width * dpr)
        canvas.height = Math.floor(viewport.height * dpr)
        canvas.style.width = `${viewport.width}px`
        canvas.style.height = `${viewport.height}px`
        canvas.className = 'block mx-auto mb-4 shadow-sm border border-slate-200 bg-white'

        const ctx = canvas.getContext('2d')
        if (!ctx) continue
        ctx.scale(dpr, dpr)

        container.appendChild(canvas)
        await page.render({ canvasContext: ctx, viewport, canvas }).promise
      }
      loading.value = false
    } catch (e) {
      if (myToken !== renderToken) return
      error.value = e instanceof Error ? e.message : String(e)
      loading.value = false
    }
  }

  watch([path, containerEl], render, { immediate: true })

  onBeforeUnmount(() => {
    renderToken++
    if (activeDoc) {
      activeDoc.destroy()
      activeDoc = null
    }
  })
</script>

<template>
  <PageToolbar />
  <a
    :href="assetUrl"
    download
    class="fixed top-3 right-[68px] z-20 bg-white/90 backdrop-blur border border-slate-200 rounded-md p-2 hover:bg-slate-50 shadow-sm"
    title="Download PDF"
    aria-label="Download PDF"
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
  <article class="mx-auto py-6" :class="width === 'wide' ? 'max-w-none px-12' : 'max-w-3xl px-8'">
    <header
      class="flex items-center justify-between mb-4"
      :class="width === 'wide' ? 'pr-48' : ''"
    >
      <Breadcrumbs :path="path" :source-id="sourceId || undefined" />
    </header>
    <h1 class="text-3xl font-bold mb-4">{{ title }}</h1>
    <p v-if="error" class="text-red-600">Failed to load PDF: {{ error }}</p>
    <p v-else-if="loading" class="text-slate-400">Loading PDF…</p>
    <div ref="containerEl" class="pdf-pages" />
  </article>
</template>
