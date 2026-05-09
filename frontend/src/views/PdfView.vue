<script setup lang="ts">
  import { computed, onBeforeUnmount, ref, watch, nextTick } from 'vue'
  import { useRoute } from 'vue-router'
  import * as pdfjs from 'pdfjs-dist/legacy/build/pdf.mjs'
  import workerUrl from 'pdfjs-dist/legacy/build/pdf.worker.mjs?url'
  import Breadcrumbs from '@/components/Breadcrumbs.vue'
  import OutlineList from '@/components/OutlineList.vue'
  import PageToolbar from '@/components/PageToolbar.vue'
  import { useReadingWidth } from '@/composables/usePrefs'

  pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

  // Cap on canvases kept in DOM at once. Hundreds of pages × full-resolution
  // bitmaps eats hundreds of MB; we evict the oldest rendered pages once we
  // pass this many.
  const MAX_LIVE_CANVASES = 8

  // How far above/below the viewport to start rendering pages. Large enough
  // that fast scrolling doesn't reveal blank placeholders.
  const RENDER_MARGIN_PX = 800

  interface OutlineEntry {
    title: string
    pageIndex: number | null
    children: OutlineEntry[]
  }

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
    const last = path.value.split('/').pop() ?? path.value
    return last.replace(/\.pdf$/i, '').replace(/[-_]/g, ' ')
  })

  const error = ref<string | null>(null)
  const loading = ref(true)
  const numPages = ref(0)
  const currentPage = ref(1)
  const pageInput = ref('1')
  const outline = ref<OutlineEntry[]>([])
  const showOutline = ref(false)

  const containerEl = ref<HTMLElement | null>(null)

  let activeDoc: pdfjs.PDFDocumentProxy | null = null
  let renderToken = 0
  let observer: IntersectionObserver | null = null

  // Per-page state. Index 0 is page 1.
  const placeholders: HTMLDivElement[] = []
  const renderedPages: Set<number> = new Set() // 1-indexed page numbers
  const renderingPages: Set<number> = new Set()
  const renderOrder: number[] = [] // for LRU eviction

  function clearAll(): void {
    if (observer) {
      observer.disconnect()
      observer = null
    }
    placeholders.length = 0
    renderedPages.clear()
    renderingPages.clear()
    renderOrder.length = 0
    if (containerEl.value) containerEl.value.innerHTML = ''
  }

  async function loadDoc(): Promise<void> {
    error.value = null
    loading.value = true
    numPages.value = 0
    currentPage.value = 1
    pageInput.value = '1'
    outline.value = []
    const myToken = ++renderToken

    if (activeDoc) {
      activeDoc.destroy()
      activeDoc = null
    }
    clearAll()

    try {
      const doc = await pdfjs.getDocument({ url: assetUrl.value }).promise
      if (myToken !== renderToken) {
        doc.destroy()
        return
      }
      activeDoc = doc
      numPages.value = doc.numPages

      await nextTick()
      const container = containerEl.value
      if (!container) return

      const containerWidth = container.clientWidth || 800

      // Build placeholders. We need each page's intrinsic size to fix the
      // aspect ratio so the scrollbar is correct from the start.
      for (let i = 1; i <= doc.numPages; i++) {
        if (myToken !== renderToken) return
        const page = await doc.getPage(i)
        const baseViewport = page.getViewport({ scale: 1 })
        const scale = containerWidth / baseViewport.width
        const w = Math.floor(baseViewport.width * scale)
        const h = Math.floor(baseViewport.height * scale)

        const ph = document.createElement('div')
        ph.dataset.pageNumber = String(i)
        ph.style.width = `${w}px`
        ph.style.height = `${h}px`
        ph.className =
          'block mx-auto mb-4 shadow-sm border border-slate-200 bg-white relative overflow-hidden'

        const label = document.createElement('div')
        label.className =
          'absolute top-2 right-2 text-[10px] text-slate-400 bg-white/70 px-1.5 py-0.5 rounded'
        label.textContent = `${i} / ${doc.numPages}`
        ph.appendChild(label)

        container.appendChild(ph)
        placeholders.push(ph)

        // Free the structural page proxy now; we'll re-fetch on actual render.
        page.cleanup()
      }

      loading.value = false

      // Set up intersection-based rendering and current-page tracking.
      observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            const n = Number((entry.target as HTMLElement).dataset.pageNumber)
            if (!n) continue
            if (entry.isIntersecting) {
              void renderPageOnce(n)
            }
          }
          updateCurrentPage()
        },
        {
          root: null,
          rootMargin: `${RENDER_MARGIN_PX}px 0px ${RENDER_MARGIN_PX}px 0px`,
          threshold: 0,
        },
      )
      for (const ph of placeholders) observer.observe(ph)

      // Outline (best-effort; many PDFs lack one).
      try {
        const raw = await doc.getOutline()
        if (myToken !== renderToken || !raw) return
        // Some pdf.js versions wrap the array in { items: [...] }.
        const rawAny = raw as any
        const items: any[] = Array.isArray(rawAny) ? rawAny : rawAny.items
        if (items?.length) {
          outline.value = await buildOutline(doc, items)
        }
      } catch (e) {
        console.warn('failed to load PDF outline', e)
      }
    } catch (e) {
      if (myToken !== renderToken) return
      error.value = e instanceof Error ? e.message : String(e)
      loading.value = false
    }
  }

  async function buildOutline(
    doc: pdfjs.PDFDocumentProxy,
    items: any[],
  ): Promise<OutlineEntry[]> {
    const out: OutlineEntry[] = []
    for (const item of items) {
      if (!item?.title) continue
      let pageIndex: number | null = null
      try {
        let dest: unknown = item.dest
        if (typeof dest === 'string') dest = await doc.getDestination(dest)
        if (Array.isArray(dest)) {
          // dest[0] is typically a page ref { num, gen }.
          const ref = dest[0] as { num: number; gen: number } | null
          if (ref && typeof ref.num === 'number') {
            pageIndex = await doc.getPageIndex(ref)
          }
        }
      } catch {
        /* unresolved destination — leave null */
      }
      const children = Array.isArray(item.items) ? await buildOutline(doc, item.items) : []
      out.push({ title: String(item.title), pageIndex, children })
    }
    return out
  }

  async function renderPageOnce(pageNum: number): Promise<void> {
    if (renderedPages.has(pageNum) || renderingPages.has(pageNum)) return
    if (!activeDoc) return
    const myToken = renderToken
    renderingPages.add(pageNum)
    try {
      const ph = placeholders[pageNum - 1]
      if (!ph) return
      const page = await activeDoc.getPage(pageNum)
      if (myToken !== renderToken) return

      const baseViewport = page.getViewport({ scale: 1 })
      const targetWidth = ph.clientWidth || 800
      const scale = targetWidth / baseViewport.width
      const viewport = page.getViewport({ scale })
      const dpr = window.devicePixelRatio || 1

      const canvas = document.createElement('canvas')
      canvas.width = Math.floor(viewport.width * dpr)
      canvas.height = Math.floor(viewport.height * dpr)
      canvas.style.width = `${viewport.width}px`
      canvas.style.height = `${viewport.height}px`
      canvas.className = 'block w-full h-full'

      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.scale(dpr, dpr)

      // Insert before the label so the label stays on top.
      ph.insertBefore(canvas, ph.firstChild)
      await page.render({ canvasContext: ctx, viewport, canvas }).promise

      if (myToken !== renderToken) return
      renderedPages.add(pageNum)
      renderOrder.push(pageNum)
      evictIfNeeded(pageNum)
    } catch {
      /* render aborted or failed — leave placeholder blank */
    } finally {
      renderingPages.delete(pageNum)
    }
  }

  function evictIfNeeded(justRendered: number): void {
    while (renderOrder.length > MAX_LIVE_CANVASES) {
      // Find the oldest page that is currently far from the viewport.
      let evictedAny = false
      for (let i = 0; i < renderOrder.length; i++) {
        const candidate = renderOrder[i]!
        if (candidate === justRendered) continue
        const ph = placeholders[candidate - 1]
        if (!ph) continue
        const rect = ph.getBoundingClientRect()
        const offscreen =
          rect.bottom < -RENDER_MARGIN_PX || rect.top > window.innerHeight + RENDER_MARGIN_PX
        if (offscreen) {
          const canvas = ph.querySelector('canvas')
          if (canvas) ph.removeChild(canvas)
          renderedPages.delete(candidate)
          renderOrder.splice(i, 1)
          evictedAny = true
          break
        }
      }
      if (!evictedAny) break
    }
  }

  function updateCurrentPage(): void {
    // Pick the placeholder whose top is closest to (but not past) the top of
    // the viewport — that's the page the user is reading.
    let best = 1
    let bestTop = -Infinity
    for (let i = 0; i < placeholders.length; i++) {
      const ph = placeholders[i]!
      const top = ph.getBoundingClientRect().top
      if (top <= 80 && top > bestTop) {
        bestTop = top
        best = i + 1
      }
    }
    if (best !== currentPage.value) {
      currentPage.value = best
      pageInput.value = String(best)
    }
  }

  function jumpToPage(n: number): void {
    if (!Number.isFinite(n) || n < 1 || n > numPages.value) return
    const ph = placeholders[n - 1]
    if (ph) ph.scrollIntoView({ block: 'start', behavior: 'auto' })
  }

  function onPageInputCommit(): void {
    const n = parseInt(pageInput.value, 10)
    if (!Number.isFinite(n)) {
      pageInput.value = String(currentPage.value)
      return
    }
    const clamped = Math.max(1, Math.min(numPages.value, n))
    pageInput.value = String(clamped)
    jumpToPage(clamped)
  }

  function jumpRelative(delta: number): void {
    jumpToPage(Math.max(1, Math.min(numPages.value, currentPage.value + delta)))
  }

  function jumpToFirst(): void {
    jumpToPage(1)
  }
  function jumpToLast(): void {
    jumpToPage(numPages.value)
  }

  function onScroll(): void {
    updateCurrentPage()
  }

  watch([path, sourceId, watchedLabel, containerEl], () => void loadDoc(), { immediate: true })

  onBeforeUnmount(() => {
    renderToken++
    if (observer) observer.disconnect()
    if (activeDoc) {
      activeDoc.destroy()
      activeDoc = null
    }
    window.removeEventListener('scroll', onScroll)
  })

  // Listen on window because the article scrolls inside the viewport.
  if (typeof window !== 'undefined') {
    window.addEventListener('scroll', onScroll, { passive: true })
  }
</script>

<template>
  <PageToolbar />
  <button
    v-if="!loading && !error"
    type="button"
    class="fixed top-3 right-[172px] z-30 bg-white/90 backdrop-blur border border-slate-200 rounded-md p-2 hover:bg-slate-50 shadow-sm"
    :class="showOutline ? 'text-blue-600' : 'text-slate-600'"
    :title="showOutline ? 'Hide outline' : 'Show outline'"
    :aria-label="showOutline ? 'Hide outline' : 'Show outline'"
    :aria-expanded="showOutline"
    @click="showOutline = !showOutline"
  >
    <svg
      xmlns="http://www.w3.org/2000/svg"
      class="w-4 h-4"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <line x1="8" y1="6" x2="21" y2="6" />
      <line x1="8" y1="12" x2="21" y2="12" />
      <line x1="8" y1="18" x2="21" y2="18" />
      <circle cx="4" cy="6" r="1" fill="currentColor" />
      <circle cx="4" cy="12" r="1" fill="currentColor" />
      <circle cx="4" cy="18" r="1" fill="currentColor" />
    </svg>
  </button>
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

  <!-- Backdrop -->
  <div
    v-if="showOutline"
    class="fixed inset-0 bg-black/20 z-30"
    aria-hidden="true"
    @click="showOutline = false"
  />

  <!-- Outline panel — slides in from the right, matches PageToc style -->
  <aside
    class="fixed top-0 right-0 h-full w-80 max-w-[85vw] bg-white border-l border-slate-200 shadow-xl z-40 transform transition-transform duration-200 ease-out flex flex-col"
    :class="showOutline ? 'translate-x-0' : 'translate-x-full'"
    aria-label="Outline"
  >
    <header class="flex items-center justify-between px-4 py-3 border-b border-slate-200">
      <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500">Outline</h2>
      <button
        type="button"
        class="p-1 -mr-1 rounded hover:bg-slate-100"
        aria-label="Close outline"
        @click="showOutline = false"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="w-4 h-4 text-slate-500"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </header>
    <div class="flex-1 overflow-y-auto py-2">
      <OutlineList
        v-if="outline.length"
        :entries="outline"
        :on-jump="jumpToPage"
        :current-page="currentPage"
      />
      <p v-else class="px-4 text-sm text-slate-400 italic">No outline available for this PDF.</p>
    </div>
  </aside>

  <article
    class="mx-auto py-6"
    :class="width === 'wide' ? 'max-w-none px-12' : 'max-w-3xl px-8'"
  >
    <header
      class="flex items-center justify-between mb-4"
      :class="width === 'wide' ? 'pr-48' : ''"
    >
      <Breadcrumbs :path="path" :source-id="sourceId || undefined" :watched-label="watchedLabel || undefined" />
    </header>
    <h1 class="text-3xl font-bold mb-4">{{ title }}</h1>
    <p v-if="error" class="text-red-600">Failed to load PDF: {{ error }}</p>
    <p v-else-if="loading" class="text-slate-400">Loading PDF…</p>
    <div ref="containerEl" class="pdf-pages relative" />

    <!-- Page navigation — sticky at the bottom of the article, centered within it -->
    <div
      v-if="!loading && numPages > 0"
      class="sticky bottom-4 flex justify-center z-30 mt-4"
    >
      <div
        class="inline-flex items-center gap-1 bg-white/95 backdrop-blur border border-slate-200 rounded-full shadow-md px-2 py-1 text-sm"
      >
        <button
          type="button"
          class="px-2 py-0.5 rounded hover:bg-slate-100 text-slate-600 disabled:opacity-30"
          :disabled="currentPage <= 1"
          title="First page"
          @click="jumpToFirst"
        >
          ⇤
        </button>
        <button
          type="button"
          class="px-2 py-0.5 rounded hover:bg-slate-100 text-slate-600 disabled:opacity-30"
          :disabled="currentPage <= 1"
          title="Previous page"
          @click="jumpRelative(-1)"
        >
          ‹
        </button>
        <input
          v-model="pageInput"
          type="text"
          inputmode="numeric"
          class="w-12 text-center border border-slate-200 rounded px-1 py-0.5 focus:outline-none focus:border-blue-400"
          @keydown.enter="onPageInputCommit"
          @blur="onPageInputCommit"
        />
        <span class="text-slate-500">/ {{ numPages }}</span>
        <button
          type="button"
          class="px-2 py-0.5 rounded hover:bg-slate-100 text-slate-600 disabled:opacity-30"
          :disabled="currentPage >= numPages"
          title="Next page"
          @click="jumpRelative(1)"
        >
          ›
        </button>
        <button
          type="button"
          class="px-2 py-0.5 rounded hover:bg-slate-100 text-slate-600 disabled:opacity-30"
          :disabled="currentPage >= numPages"
          title="Last page"
          @click="jumpToLast"
        >
          ⇥
        </button>
      </div>
    </div>
  </article>
</template>
