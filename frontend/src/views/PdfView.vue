<script setup lang="ts">
  import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
  import { useRoute } from 'vue-router'
  import * as pdfjs from 'pdfjs-dist/legacy/build/pdf.mjs'
  import workerUrl from 'pdfjs-dist/legacy/build/pdf.worker.mjs?url'
  import Breadcrumbs from '@/components/Breadcrumbs.vue'
  import OutlineList from '@/components/OutlineList.vue'
  import PageToolbar from '@/components/PageToolbar.vue'
  import { usePdfLayout, useReadingWidth } from '@/composables/usePrefs'

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
  const { layout: pdfLayout, toggle: togglePdfLayout } = usePdfLayout()

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
  let resizeObserver: ResizeObserver | null = null
  let relayoutTimer: number | null = null

  // Per-page state. Index 0 is page 1.
  const placeholders: HTMLDivElement[] = []
  const intrinsicSizes: { w: number; h: number }[] = [] // unscaled (scale=1) dims
  const renderedScales: Map<number, number> = new Map() // pageNum -> scale at render
  const renderedPages: Set<number> = new Set() // 1-indexed page numbers
  const renderingPages: Set<number> = new Set()
  const renderOrder: number[] = [] // for LRU eviction

  function clearAll(): void {
    if (observer) {
      observer.disconnect()
      observer = null
    }
    placeholders.length = 0
    intrinsicSizes.length = 0
    renderedScales.clear()
    renderedPages.clear()
    renderingPages.clear()
    renderOrder.length = 0
    if (containerEl.value) containerEl.value.innerHTML = ''
  }

  // Available dimensions for a single page in the current layout. In single
  // mode we fit to viewport height (minus the sticky toolbar at the bottom);
  // in scroll mode we fit to container width.
  function availableDims(): { w: number; h: number } {
    const container = containerEl.value
    const w = container?.clientWidth || 800
    // In single mode the page must fully fit the viewport — otherwise the
    // page overflows, the body grows a scrollbar, and wheel scrolls instead
    // of paginating. Measure the container's actual top offset so the page
    // height excludes the article header (breadcrumbs+title) and our sticky
    // bottom nav. The 72px allowance covers the nav bar + bottom margin.
    const containerTop = container?.getBoundingClientRect().top ?? 0
    const h = Math.max(200, Math.floor(window.innerHeight - containerTop - 72))
    return { w, h }
  }

  function targetScaleFor(pageNum: number): number {
    const intr = intrinsicSizes[pageNum - 1]
    if (!intr) return 1
    const { w, h } = availableDims()
    if (pdfLayout.value === 'single') {
      // Fit-to-height: scale so the full page height fits in the viewport.
      // Width may end up narrower than the screen, which is fine — the page
      // is centered horizontally.
      return h / intr.h
    }
    return w / intr.w
  }

  function applyPlaceholderSize(pageNum: number): void {
    const ph = placeholders[pageNum - 1]
    const intr = intrinsicSizes[pageNum - 1]
    if (!ph || !intr) return
    const scale = targetScaleFor(pageNum)
    ph.style.width = `${Math.floor(intr.w * scale)}px`
    ph.style.height = `${Math.floor(intr.h * scale)}px`
  }

  function isPlaceholderVisible(pageNum: number): boolean {
    if (pdfLayout.value === 'single') return pageNum === currentPage.value
    return true
  }

  function applyLayoutVisibility(): void {
    for (let i = 1; i <= placeholders.length; i++) {
      const ph = placeholders[i - 1]!
      ph.style.display = isPlaceholderVisible(i) ? '' : 'none'
    }
  }

  // Drop canvases that no longer match the current layout's scale; the
  // intersection observer (or single-mode jump) will re-render them.
  function discardStaleRenders(): void {
    for (const pageNum of Array.from(renderedPages)) {
      const prev = renderedScales.get(pageNum)
      const next = targetScaleFor(pageNum)
      if (prev === undefined) continue
      if (Math.abs(prev - next) / next < 0.01) continue // within 1% — keep
      const ph = placeholders[pageNum - 1]
      if (!ph) continue
      const canvas = ph.querySelector('canvas')
      if (canvas) ph.removeChild(canvas)
      const textLayerDiv = ph.querySelector('.textLayer')
      if (textLayerDiv) ph.removeChild(textLayerDiv)
      renderedPages.delete(pageNum)
      renderedScales.delete(pageNum)
      const idx = renderOrder.indexOf(pageNum)
      if (idx !== -1) renderOrder.splice(idx, 1)
    }
  }

  function relayout(): void {
    if (!placeholders.length) return
    for (let i = 1; i <= placeholders.length; i++) applyPlaceholderSize(i)
    applyLayoutVisibility()
    discardStaleRenders()
    if (pdfLayout.value === 'single') {
      // Render the current page (and pre-render neighbors) right away — no
      // scroll happens to retrigger the IntersectionObserver.
      void renderPageOnce(currentPage.value)
      if (currentPage.value + 1 <= numPages.value) void renderPageOnce(currentPage.value + 1)
      if (currentPage.value - 1 >= 1) void renderPageOnce(currentPage.value - 1)
    } else {
      // Scroll mode: discardStaleRenders dropped canvases that no longer
      // match the new scale, but the IntersectionObserver only fires on
      // visibility *changes* — pages already in view won't refire. Manually
      // re-render anything currently in (or near) the viewport.
      for (let i = 1; i <= placeholders.length; i++) {
        const ph = placeholders[i - 1]!
        const rect = ph.getBoundingClientRect()
        const inView =
          rect.bottom > -RENDER_MARGIN_PX && rect.top < window.innerHeight + RENDER_MARGIN_PX
        if (inView) void renderPageOnce(i)
      }
    }
  }

  function scheduleRelayout(): void {
    if (relayoutTimer !== null) window.clearTimeout(relayoutTimer)
    relayoutTimer = window.setTimeout(() => {
      relayoutTimer = null
      relayout()
    }, 80)
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

      // Build placeholders. We need each page's intrinsic size to fix the
      // aspect ratio so the scrollbar is correct from the start.
      for (let i = 1; i <= doc.numPages; i++) {
        if (myToken !== renderToken) return
        const page = await doc.getPage(i)
        const baseViewport = page.getViewport({ scale: 1 })
        intrinsicSizes.push({ w: baseViewport.width, h: baseViewport.height })

        const ph = document.createElement('div')
        ph.dataset.pageNumber = String(i)
        ph.className =
          'block mx-auto mb-4 shadow-sm border border-slate-200 bg-white relative overflow-hidden'

        const label = document.createElement('div')
        label.className =
          'absolute top-2 right-2 text-[10px] text-slate-400 bg-white/70 px-1.5 py-0.5 rounded'
        label.textContent = `${i} / ${doc.numPages}`
        ph.appendChild(label)

        container.appendChild(ph)
        placeholders.push(ph)
        applyPlaceholderSize(i)

        // Free the structural page proxy now; we'll re-fetch on actual render.
        page.cleanup()
      }

      applyLayoutVisibility()
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

  async function buildOutline(doc: pdfjs.PDFDocumentProxy, items: any[]): Promise<OutlineEntry[]> {
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

      const scale = targetScaleFor(pageNum)
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

      // Build a selectable text layer above the canvas. Cheap relative to the
      // canvas render and bounded by MAX_LIVE_CANVASES via eviction below.
      try {
        const textLayerDiv = document.createElement('div')
        textLayerDiv.className = 'textLayer'
        textLayerDiv.style.width = `${viewport.width}px`
        textLayerDiv.style.height = `${viewport.height}px`
        // pdf.js's TextLayer reads --scale-factor / --total-scale-factor.
        textLayerDiv.style.setProperty('--scale-factor', String(viewport.scale))
        textLayerDiv.style.setProperty('--total-scale-factor', String(viewport.scale))
        ph.insertBefore(textLayerDiv, canvas.nextSibling)
        const textLayer = new pdfjs.TextLayer({
          textContentSource: page.streamTextContent(),
          container: textLayerDiv,
          viewport,
        })
        await textLayer.render()
      } catch {
        /* text layer is best-effort; image-only PDFs will simply have none */
      }

      renderedPages.add(pageNum)
      renderedScales.set(pageNum, scale)
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
          const textLayerDiv = ph.querySelector('.textLayer')
          if (textLayerDiv) ph.removeChild(textLayerDiv)
          renderedPages.delete(candidate)
          renderedScales.delete(candidate)
          renderOrder.splice(i, 1)
          evictedAny = true
          break
        }
      }
      if (!evictedAny) break
    }
  }

  function updateCurrentPage(): void {
    if (pdfLayout.value === 'single') return // current page is set explicitly
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
    if (pdfLayout.value === 'single') {
      currentPage.value = n
      pageInput.value = String(n)
      applyLayoutVisibility()
      window.scrollTo({ top: 0, behavior: 'auto' })
      void renderPageOnce(n)
      // Pre-render neighbors so paging feels instant.
      if (n + 1 <= numPages.value) void renderPageOnce(n + 1)
      if (n - 1 >= 1) void renderPageOnce(n - 1)
      return
    }
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

  function onKeydown(e: KeyboardEvent): void {
    // Don't hijack typing in the page-input box or any other input.
    const t = e.target as HTMLElement | null
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
    if (numPages.value === 0) return
    switch (e.key) {
      case 'ArrowRight':
      case 'PageDown':
        e.preventDefault()
        jumpRelative(1)
        break
      case 'ArrowLeft':
      case 'PageUp':
        e.preventDefault()
        jumpRelative(-1)
        break
      case ' ':
        if (pdfLayout.value === 'single') {
          e.preventDefault()
          jumpRelative(e.shiftKey ? -1 : 1)
        }
        break
      case 'Home':
        if (pdfLayout.value === 'single') {
          e.preventDefault()
          jumpToFirst()
        }
        break
      case 'End':
        if (pdfLayout.value === 'single') {
          e.preventDefault()
          jumpToLast()
        }
        break
    }
  }

  function onWheel(e: WheelEvent): void {
    if (pdfLayout.value !== 'single') return
    if (Math.abs(e.deltaY) < 20) return
    e.preventDefault()
    jumpRelative(e.deltaY > 0 ? 1 : -1)
  }

  watch([path, sourceId, watchedLabel, containerEl], () => void loadDoc(), { immediate: true })
  watch([pdfLayout, width], () => scheduleRelayout())

  // In single-page mode, suppress the body scrollbar entirely — the page is
  // sized to fit the viewport and wheel events drive pagination, not scroll.
  watch(
    pdfLayout,
    (v) => {
      if (typeof document === 'undefined') return
      document.documentElement.style.overflow = v === 'single' ? 'hidden' : ''
    },
    { immediate: true },
  )

  onMounted(() => {
    if (containerEl.value) {
      resizeObserver = new ResizeObserver(() => scheduleRelayout())
      resizeObserver.observe(containerEl.value)
    }
    window.addEventListener('keydown', onKeydown)
    window.addEventListener('wheel', onWheel, { passive: false })
  })

  onBeforeUnmount(() => {
    renderToken++
    if (relayoutTimer !== null) {
      window.clearTimeout(relayoutTimer)
      relayoutTimer = null
    }
    if (observer) observer.disconnect()
    if (resizeObserver) {
      resizeObserver.disconnect()
      resizeObserver = null
    }
    if (activeDoc) {
      activeDoc.destroy()
      activeDoc = null
    }
    window.removeEventListener('scroll', onScroll)
    window.removeEventListener('keydown', onKeydown)
    window.removeEventListener('wheel', onWheel)
    if (typeof document !== 'undefined') {
      document.documentElement.style.overflow = ''
    }
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
  <button
    v-if="!loading && !error"
    type="button"
    class="fixed top-3 right-[120px] z-30 bg-white/90 backdrop-blur border border-slate-200 rounded-md p-2 hover:bg-slate-50 shadow-sm"
    :class="pdfLayout === 'single' ? 'text-blue-600' : 'text-slate-600'"
    :title="pdfLayout === 'single' ? 'Switch to scroll layout' : 'Switch to single-page layout'"
    :aria-label="
      pdfLayout === 'single' ? 'Switch to scroll layout' : 'Switch to single-page layout'
    "
    :aria-pressed="pdfLayout === 'single'"
    @click="togglePdfLayout"
  >
    <svg
      v-if="pdfLayout === 'single'"
      xmlns="http://www.w3.org/2000/svg"
      class="w-4 h-4"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <rect x="6" y="3" width="12" height="14" rx="1" />
      <path d="M9 20h6" />
    </svg>
    <svg
      v-else
      xmlns="http://www.w3.org/2000/svg"
      class="w-4 h-4"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <rect x="4" y="3" width="16" height="6" rx="1" />
      <rect x="4" y="11" width="16" height="6" rx="1" />
      <path d="M8 21h8" />
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
    class="mx-auto"
    :class="[
      pdfLayout === 'single' ? 'py-2' : 'py-6',
      width === 'wide' ? 'max-w-none px-12' : 'max-w-3xl px-8',
    ]"
  >
    <header
      v-if="pdfLayout !== 'single'"
      class="flex items-center justify-between mb-4"
      :class="width === 'wide' ? 'pr-48' : ''"
    >
      <Breadcrumbs
        :path="path"
        :source-id="sourceId || undefined"
        :watched-label="watchedLabel || undefined"
      />
    </header>
    <h1 v-if="pdfLayout !== 'single'" class="text-3xl font-bold mb-4">{{ title }}</h1>
    <p v-if="error" class="text-red-600">Failed to load PDF: {{ error }}</p>
    <p v-else-if="loading" class="text-slate-400">Loading PDF…</p>
    <div ref="containerEl" class="pdf-pages relative" />

    <!-- Page navigation — sticky at the bottom of the article, centered within it -->
    <div v-if="!loading && numPages > 0" class="sticky bottom-4 flex justify-center z-30 mt-4">
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

<style>
  /* Minimal text-layer styles from pdfjs-dist/web/pdf_viewer.css. The text
     layer is positioned absolutely over each rendered canvas; spans are
     transparent so the canvas shows through but text is selectable. */
  .pdf-pages .textLayer {
    position: absolute;
    inset: 0;
    overflow: clip;
    opacity: 1;
    line-height: 1;
    text-align: initial;
    -webkit-text-size-adjust: none;
    -moz-text-size-adjust: none;
    text-size-adjust: none;
    forced-color-adjust: none;
    transform-origin: 0 0;
    caret-color: CanvasText;
    z-index: 0;
    --min-font-size: 1;
    --text-scale-factor: calc(var(--total-scale-factor) * var(--min-font-size));
    --min-font-size-inv: calc(1 / var(--min-font-size));
  }
  .pdf-pages .textLayer :is(span, br) {
    color: transparent;
    position: absolute;
    white-space: pre;
    cursor: text;
    transform-origin: 0% 0%;
  }
  .pdf-pages .textLayer > :not(.markedContent),
  .pdf-pages .textLayer .markedContent span:not(.markedContent) {
    z-index: 1;
    --font-height: 0;
    font-size: calc(var(--text-scale-factor) * var(--font-height));
    --scale-x: 1;
    --rotate: 0deg;
    transform: rotate(var(--rotate)) scaleX(var(--scale-x)) scale(var(--min-font-size-inv));
  }
  .pdf-pages .textLayer .markedContent {
    display: contents;
  }
  .pdf-pages .textLayer span[role='img'] {
    -webkit-user-select: none;
    -moz-user-select: none;
    user-select: none;
    cursor: default;
  }
  .pdf-pages .textLayer ::selection {
    background: rgba(0, 100, 255, 0.25);
  }
  .pdf-pages .textLayer ::-moz-selection {
    background: rgba(0, 100, 255, 0.25);
  }
  .pdf-pages .textLayer br::selection {
    background: transparent;
  }
  .pdf-pages .textLayer .endOfContent {
    display: block;
    position: absolute;
    inset: 100% 0 0;
    z-index: 0;
    cursor: default;
    -webkit-user-select: none;
    -moz-user-select: none;
    user-select: none;
  }
  .pdf-pages .textLayer.selecting .endOfContent {
    top: 0;
  }
</style>
