<script setup lang="ts">
  import { computed, onBeforeUnmount, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import Breadcrumbs from '@/components/Breadcrumbs.vue'
  import PageToolbar from '@/components/PageToolbar.vue'
  import { useReadingWidth } from '@/composables/usePrefs'
  // Importing the foliate entry registers the <foliate-view> custom element and
  // pulls in our R6 note about its default script-stripping. See src/lib/ebook.ts.
  import '@/lib/ebook'

  // Viewer for e-book formats (EPUB, MOBI, KF8/AZW3, FB2, CBZ), rendered by
  // foliate-js. foliate owns pagination, the content iframe, and resource
  // loading; this view just wires the asset URL in and surfaces a TOC, page
  // nav, and download. R6 holds via foliate's default (book scripts stripped at
  // load) — see src/lib/ebook.ts. Same scaffold family as PdfView.

  // A TOC entry flattened from foliate's nested book.toc. `href` is what we
  // hand back to view.goTo(); `depth` drives indentation.
  interface TocItem {
    label: string
    href: string
    depth: number
  }

  // The <foliate-view> element. Typed loosely — foliate ships no declarations
  // and we only touch a handful of methods/events.
  interface FoliateView extends HTMLElement {
    open(src: string): Promise<void>
    goTo(target: string | number): Promise<void>
    goToFraction(frac: number): Promise<void>
    goLeft(): void
    goRight(): void
    book?: { toc?: unknown[]; dir?: 'ltr' | 'rtl' }
  }

  // The slice of foliate's `relocate` detail we read. `location` is a
  // book-wide page-like counter; `tocItem.label` is the current chapter.
  interface RelocateDetail {
    fraction?: number
    location?: { current?: number; total?: number }
    tocItem?: { label?: string } | null
  }

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
    const last = path.value.split('/').pop() ?? path.value
    return last
      .replace(/\.(epub|mobi|azw3?|kf8|prc|fb2(\.zip)?|fbz|cbz)$/i, '')
      .replace(/[-_]/g, ' ')
  })

  const error = ref<string | null>(null)
  const loading = ref(true)
  const toc = ref<TocItem[]>([])
  const showToc = ref(false)
  // Reading progress as a fraction (0–1) reported by foliate's relocate event.
  const fraction = ref(0)
  // Book-wide location counter (foliate's `location`, roughly a page number),
  // and the current chapter label, both from relocate. null until first event.
  const locCurrent = ref<number | null>(null)
  const locTotal = ref<number | null>(null)
  const chapter = ref<string>('')

  const viewEl = ref<FoliateView | null>(null)
  // Bumps on each (re)load so a slow in-flight open can detect it's stale.
  let loadToken = 0

  function flattenToc(items: unknown[], depth: number, out: TocItem[]): void {
    for (const raw of items) {
      const item = raw as { label?: string; href?: string; subitems?: unknown[] }
      if (item.href && item.label) {
        out.push({ label: item.label.trim(), href: item.href, depth })
      }
      if (Array.isArray(item.subitems) && item.subitems.length) {
        flattenToc(item.subitems, depth + 1, out)
      }
    }
  }

  async function loadBook(): Promise<void> {
    const el = viewEl.value
    if (!el) return
    const myToken = ++loadToken
    error.value = null
    loading.value = true
    toc.value = []
    fraction.value = 0
    locCurrent.value = null
    locTotal.value = null
    chapter.value = ''

    // relocate fires on every page turn with the current location/fraction.
    el.addEventListener('relocate', (e: Event) => {
      const detail = (e as CustomEvent).detail as RelocateDetail | undefined
      if (!detail) return
      if (typeof detail.fraction === 'number') fraction.value = detail.fraction
      if (typeof detail.location?.current === 'number') {
        // foliate's location.current is 0-based; show it 1-based.
        locCurrent.value = detail.location.current + 1
      }
      if (typeof detail.location?.total === 'number') locTotal.value = detail.location.total
      chapter.value = detail.tocItem?.label?.trim() ?? ''
    })

    try {
      await el.open(assetUrl.value)
      if (myToken !== loadToken) return
      const rawToc = el.book?.toc
      if (Array.isArray(rawToc)) {
        const flat: TocItem[] = []
        flattenToc(rawToc, 0, flat)
        toc.value = flat
      }
      loading.value = false
    } catch (e) {
      if (myToken !== loadToken) return
      error.value = e instanceof Error ? e.message : String(e)
      loading.value = false
    }
  }

  function goToHref(href: string): void {
    void viewEl.value?.goTo(href)
    showToc.value = false
  }

  // Seek to a fraction of the whole book — used by clicking the progress bar.
  function seekToFraction(frac: number): void {
    void viewEl.value?.goToFraction(Math.max(0, Math.min(1, frac)))
  }

  function onProgressClick(e: MouseEvent): void {
    const bar = e.currentTarget as HTMLElement
    const rect = bar.getBoundingClientRect()
    if (rect.width <= 0) return
    seekToFraction((e.clientX - rect.left) / rect.width)
  }

  // Mouse wheel turns pages (foliate paginates, so there's nothing to scroll).
  // Throttled to one turn per gesture-ish via a small cooldown so a single
  // trackpad flick doesn't skip several pages. Ignore tiny deltas.
  let wheelCooldown = false
  function onWheel(e: WheelEvent): void {
    if (loading.value || error.value) return
    if (Math.abs(e.deltaY) < 8) return
    e.preventDefault()
    if (wheelCooldown) return
    wheelCooldown = true
    window.setTimeout(() => (wheelCooldown = false), 220)
    if (e.deltaY > 0) viewEl.value?.goRight()
    else viewEl.value?.goLeft()
  }

  function onKeydown(e: KeyboardEvent): void {
    const t = e.target as HTMLElement | null
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
    if (loading.value || error.value) return
    switch (e.key) {
      case 'ArrowRight':
      case 'PageDown':
      case ' ':
        e.preventDefault()
        viewEl.value?.goRight()
        break
      case 'ArrowLeft':
      case 'PageUp':
        e.preventDefault()
        viewEl.value?.goLeft()
        break
    }
  }

  watch([viewEl, assetUrl], () => void loadBook())

  watch(
    () => !loading.value && !error.value,
    (ready) => {
      if (ready) window.addEventListener('keydown', onKeydown)
      else window.removeEventListener('keydown', onKeydown)
    },
  )

  onBeforeUnmount(() => {
    loadToken++
    window.removeEventListener('keydown', onKeydown)
  })
</script>

<template>
  <PageToolbar />
  <button
    v-if="!loading && !error && toc.length"
    type="button"
    class="fixed top-[52px] right-[24px] z-30 bg-white/90 backdrop-blur border border-slate-200 rounded-md p-2 hover:bg-slate-50 shadow-sm"
    :class="showToc ? 'text-blue-600' : 'text-slate-600'"
    :title="showToc ? 'Hide contents' : 'Show contents'"
    :aria-label="showToc ? 'Hide contents' : 'Show contents'"
    :aria-expanded="showToc"
    @click="showToc = !showToc"
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
    title="Download book"
    aria-label="Download book"
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
    v-if="showToc"
    class="fixed inset-0 bg-black/20 z-30"
    aria-hidden="true"
    @click="showToc = false"
  />

  <!-- Contents panel — slides in from the right, matches PdfView's outline -->
  <aside
    class="fixed top-0 right-0 h-full w-80 max-w-[85vw] bg-white border-l border-slate-200 shadow-xl z-40 transform transition-transform duration-200 ease-out flex flex-col"
    :class="showToc ? 'translate-x-0' : 'translate-x-full'"
    aria-label="Contents"
  >
    <header class="flex items-center justify-between px-4 py-3 border-b border-slate-200">
      <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500">Contents</h2>
      <button
        type="button"
        class="p-1 -mr-1 rounded hover:bg-slate-100"
        aria-label="Close contents"
        @click="showToc = false"
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
      <ul v-if="toc.length" class="text-sm">
        <li v-for="(item, i) in toc" :key="i">
          <button
            type="button"
            class="w-full text-left truncate py-1 pr-3 border-l-2 border-transparent transition-colors hover:bg-slate-50 hover:text-slate-900 text-slate-700"
            :style="{ paddingLeft: `${12 + item.depth * 16}px` }"
            @click="goToHref(item.href)"
          >
            {{ item.label }}
          </button>
        </li>
      </ul>
      <p v-else class="px-4 text-sm text-slate-400 italic">No contents available.</p>
    </div>
  </aside>

  <article class="mx-auto py-4" :class="width === 'wide' ? 'max-w-none px-12' : 'max-w-4xl px-8'">
    <header class="mb-4">
      <Breadcrumbs
        :path="path"
        :source-id="sourceId || undefined"
        :watched-label="watchedLabel || undefined"
      />
    </header>
    <h1 class="text-xl font-bold mb-4 text-slate-800">{{ title }}</h1>
    <p v-if="error" class="text-red-600">Failed to open book: {{ error }}</p>
    <p v-else-if="loading" class="text-slate-400">Opening book…</p>

    <!-- foliate renders into this element. Fixed reading height; foliate
         paginates within it. Prev/next regions sit on either side, and the
         mouse wheel turns pages (.prevent forces a non-passive listener so we
         can stop the page from scrolling). -->
    <div v-show="!loading && !error" class="relative" @wheel.prevent="onWheel">
      <button
        type="button"
        class="absolute left-0 top-0 bottom-0 w-12 z-10 flex items-center justify-center text-slate-300 hover:text-slate-600 hover:bg-slate-50/60 transition"
        title="Previous page"
        aria-label="Previous page"
        @click="viewEl?.goLeft()"
      >
        ‹
      </button>
      <button
        type="button"
        class="absolute right-0 top-0 bottom-0 w-12 z-10 flex items-center justify-center text-slate-300 hover:text-slate-600 hover:bg-slate-50/60 transition"
        title="Next page"
        aria-label="Next page"
        @click="viewEl?.goRight()"
      >
        ›
      </button>
      <!-- eslint-disable-next-line vue/no-undef-components -->
      <foliate-view
        ref="viewEl"
        class="block h-[80vh] w-full border border-slate-200 rounded-md bg-white"
      />
    </div>

    <!-- Bottom navigation — mirrors PdfView's sticky pill. prev/next, a
         clickable progress bar (seek), location counter, and chapter label. -->
    <div v-if="!loading && !error" class="sticky bottom-4 mt-4 flex justify-center z-30">
      <div
        class="inline-flex items-center gap-2 bg-white/95 backdrop-blur border border-slate-200 rounded-full shadow-md px-2 py-1 text-sm"
      >
        <button
          type="button"
          class="px-2 py-0.5 rounded hover:bg-slate-100 text-slate-600"
          title="Previous page"
          aria-label="Previous page"
          @click="viewEl?.goLeft()"
        >
          ‹
        </button>

        <!-- Current chapter (hidden when unknown / on narrow screens) -->
        <span
          v-if="chapter"
          class="hidden sm:block max-w-[14rem] truncate text-slate-500"
          :title="chapter"
        >
          {{ chapter }}
        </span>

        <!-- Clickable progress bar: click to seek to that fraction of the book. -->
        <button
          type="button"
          class="group relative h-3 w-32 flex items-center"
          :aria-label="`Seek — ${Math.round(fraction * 100)} percent`"
          @click="onProgressClick"
        >
          <span class="absolute inset-x-0 h-1.5 rounded-full bg-slate-200 overflow-hidden">
            <span class="block h-full bg-blue-500" :style="{ width: `${fraction * 100}%` }" />
          </span>
        </button>

        <span class="tabular-nums text-slate-500 whitespace-nowrap">
          <template v-if="locCurrent != null && locTotal != null"
            >{{ locCurrent }} / {{ locTotal }}</template
          >
          <template v-else>{{ Math.round(fraction * 100) }}%</template>
        </span>

        <button
          type="button"
          class="px-2 py-0.5 rounded hover:bg-slate-100 text-slate-600"
          title="Next page"
          aria-label="Next page"
          @click="viewEl?.goRight()"
        >
          ›
        </button>
      </div>
    </div>
  </article>
</template>
