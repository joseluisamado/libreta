<script setup lang="ts">
  import { computed, onBeforeUnmount, ref, watch } from 'vue'
  import { pdfjs, PDF_DOC_OPTIONS } from '@/lib/pdf'
  import { renderMarkdown } from '@/markdown'

  // First-page PDF thumbnails, cached as data URLs keyed by raw URL and shared
  // across every tile for the session (module scope, not per-instance), so
  // re-entering a folder / toggling view / resizing skips the re-parse.
  const pdfThumbCache = new Map<string, string>()

  // A tile in the preview grid. Renders a self-generated preview of the file
  // content — rendered markdown for pages, the first page of a PDF drawn to a
  // canvas (no native viewer chrome), the image itself, a raw snippet for
  // plain text — with the filename below. Clicking navigates (RouterLink) or
  // downloads (plain <a>) depending on `external`.
  type TileKind = 'folder' | 'pdf' | 'page' | 'image' | 'drawio' | 'text' | 'binary'

  const props = defineProps<{
    to: string
    label: string
    kind: TileKind
    size: number
    rawUrl?: string
    // When true, render a plain <a> (download / open external viewer)
    // instead of a RouterLink.
    external?: boolean
    downloadName?: string
  }>()

  defineEmits<{
    rename: []
    delete: []
  }>()

  // The markdown thumbnail renders at this nominal width then scales to fit
  // the tile, so the layout looks like a shrunk page rather than reflowed
  // narrow text. Tuned to read as "a document".
  const RENDER_WIDTH = 480
  // How much text to pull for a preview. Enough to fill a tile; not the whole
  // file (these are thumbnails, and big files would be wasteful to fetch).
  const SNIPPET_CHARS = 4000

  // Strip a leading YAML frontmatter block so the thumbnail shows the body,
  // not the "created/updated/tags" metadata — matching the regular editor,
  // which renders the already-parsed body. Mirrors the `---\n…\n---` fence
  // that python-frontmatter writes on save.
  function stripFrontmatter(text: string): string {
    const m = /^\uFEFF?---\r?\n[\s\S]*?\r?\n---\r?\n?/.exec(text)
    return m ? text.slice(m[0].length) : text
  }

  const renderedHtml = ref<string>('')
  const rawSnippet = ref<string>('')
  const previewError = ref(false)
  const loading = ref(false)

  // page → rendered markdown HTML; text → raw monospace snippet.
  const isMarkdown = computed(() => props.kind === 'page')
  const isText = computed(() => props.kind === 'text')
  const isImage = computed(() => props.kind === 'image')
  const isPdf = computed(() => props.kind === 'pdf')
  const isFolder = computed(() => props.kind === 'folder')

  async function loadTextual(): Promise<void> {
    if (!props.rawUrl || (!isMarkdown.value && !isText.value)) return
    loading.value = true
    previewError.value = false
    try {
      const r = await fetch(props.rawUrl)
      if (!r.ok) throw new Error(String(r.status))
      const full = await r.text()
      if (isMarkdown.value) {
        // Strip frontmatter first so it doesn't eat the snippet budget, then
        // render. No source context: relative asset links won't resolve, which
        // is fine for a thumbnail and avoids broken-image fetch storms.
        renderedHtml.value = renderMarkdown(stripFrontmatter(full).slice(0, SNIPPET_CHARS))
      } else {
        rawSnippet.value = full.slice(0, SNIPPET_CHARS)
      }
    } catch {
      previewError.value = true
    } finally {
      loading.value = false
    }
  }

  // ── PDF first-page render ────────────────────────────────────────────────
  //
  // The rendered first page is cached as a data URL (see pdfThumbCache at
  // module scope) so re-entering the folder, toggling list/preview, or
  // resizing reuses the bitmap instead of re-parsing the PDF.
  const pdfThumbnail = ref<string>('')
  // Bumps on every (re)load so a slow in-flight render can detect it's stale.
  let renderToken = 0

  async function loadPdf(): Promise<void> {
    if (!props.rawUrl || !isPdf.value) return
    const url = props.rawUrl
    const myToken = ++renderToken

    const cached = pdfThumbCache.get(url)
    if (cached) {
      pdfThumbnail.value = cached
      loading.value = false
      previewError.value = false
      return
    }

    loading.value = true
    previewError.value = false
    let doc: pdfjs.PDFDocumentProxy | null = null
    try {
      doc = await pdfjs.getDocument({ url, ...PDF_DOC_OPTIONS }).promise
      const page = await doc.getPage(1)
      if (myToken !== renderToken) return

      // Fit the first page into the preview box at device resolution, then
      // export to a data URL we can cache and show via <img>.
      const base = page.getViewport({ scale: 1 })
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const scale = (RENDER_WIDTH / base.width) * dpr
      const viewport = page.getViewport({ scale })
      const canvas = document.createElement('canvas')
      canvas.width = Math.floor(viewport.width)
      canvas.height = Math.floor(viewport.height)
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      await page.render({ canvasContext: ctx, viewport, canvas }).promise
      if (myToken !== renderToken) return

      const dataUrl = canvas.toDataURL('image/webp', 0.8)
      pdfThumbCache.set(url, dataUrl)
      pdfThumbnail.value = dataUrl
    } catch {
      if (myToken === renderToken) previewError.value = true
    } finally {
      doc?.destroy()
      if (myToken === renderToken) loading.value = false
    }
  }

  watch(
    () => [props.rawUrl, props.kind] as const,
    () => {
      renderedHtml.value = ''
      rawSnippet.value = ''
      pdfThumbnail.value = ''
      void loadTextual()
      void loadPdf()
    },
    { immediate: true },
  )

  // Invalidate any slow in-flight render once this tile goes away.
  onBeforeUnmount(() => {
    renderToken++
  })

  // Badge shown as the kind chip and as the fallback when no preview renders.
  function badge(): string {
    switch (props.kind) {
      case 'pdf':
        return 'PDF'
      case 'page':
        return 'MD'
      case 'drawio':
        return 'DRAW'
      case 'image':
        return 'IMG'
      case 'text':
        return 'TXT'
      default:
        return 'BIN'
    }
  }

  function badgeColor(): string {
    switch (props.kind) {
      case 'pdf':
        return 'text-rose-500'
      case 'page':
        return 'text-sky-500'
      case 'drawio':
        return 'text-orange-500'
      case 'image':
        return 'text-emerald-500'
      case 'text':
        return 'text-violet-500'
      default:
        return 'text-slate-500'
    }
  }

  // Preview pane height: a 4:3-ish box relative to tile width.
  const previewHeight = computed(() => Math.round(props.size * 0.7))
  // Scale factor from the nominal render width down to the actual tile width.
  const renderScale = computed(() => props.size / RENDER_WIDTH)
</script>

<template>
  <div class="group relative flex flex-col">
    <component
      :is="external ? 'a' : 'RouterLink'"
      :to="external ? undefined : to"
      :href="external ? to : undefined"
      :download="downloadName"
      class="block rounded-lg border border-slate-200 overflow-hidden bg-white hover:border-blue-400 hover:shadow-sm transition"
    >
      <!-- Preview pane -->
      <div
        class="relative bg-slate-50 overflow-hidden flex items-center justify-center"
        :style="{ height: `${previewHeight}px` }"
      >
        <!-- Folder -->
        <svg
          v-if="isFolder"
          xmlns="http://www.w3.org/2000/svg"
          class="w-1/2 h-1/2 text-amber-400"
          viewBox="0 0 24 24"
          fill="currentColor"
          stroke="none"
        >
          <path d="M2 6a2 2 0 0 1 2-2h5l2 2h9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6z" />
        </svg>

        <!-- Image -->
        <img
          v-else-if="isImage && rawUrl"
          :src="rawUrl"
          :alt="label"
          class="w-full h-full object-cover"
          loading="lazy"
        />

        <!-- PDF first page, rendered by us (no native viewer chrome), cached -->
        <template v-else-if="isPdf">
          <div v-if="loading && !pdfThumbnail" class="text-[11px] text-slate-400">Loading…</div>
          <span
            v-else-if="previewError && !pdfThumbnail"
            class="text-2xl font-bold"
            :class="badgeColor()"
            >{{ badge() }}</span
          >
          <img
            v-else-if="pdfThumbnail"
            :src="pdfThumbnail"
            :alt="label"
            class="w-full h-full object-contain object-top bg-white"
          />
        </template>

        <!-- Rendered markdown thumbnail -->
        <template v-else-if="isMarkdown">
          <div v-if="loading" class="text-[11px] text-slate-400">Loading…</div>
          <span
            v-else-if="previewError || !renderedHtml"
            class="text-2xl font-bold"
            :class="badgeColor()"
            >{{ badge() }}</span
          >
          <!-- Render at a fixed width, then scale down: looks like a page. -->
          <div
            v-else
            class="absolute top-0 left-0 origin-top-left bg-white pointer-events-none"
            :style="{
              width: `${RENDER_WIDTH}px`,
              transform: `scale(${renderScale})`,
            }"
          >
            <div class="prose prose-sm p-3" v-html="renderedHtml" />
          </div>
        </template>

        <!-- Plain-text snippet -->
        <template v-else-if="isText">
          <div v-if="loading" class="text-[11px] text-slate-400">Loading…</div>
          <pre
            v-else-if="rawSnippet"
            class="w-full h-full overflow-hidden p-2 text-[9px] leading-snug text-slate-600 whitespace-pre-wrap break-words"
            >{{ rawSnippet }}</pre
          >
          <span v-else class="text-2xl font-bold" :class="badgeColor()">{{ badge() }}</span>
        </template>

        <!-- Fallback badge (binary, drawio, missing raw url) -->
        <span v-else class="text-2xl font-bold" :class="badgeColor()">{{ badge() }}</span>

        <!-- Top-right kind chip -->
        <span
          v-if="!isFolder"
          class="absolute top-1 right-1 px-1 rounded bg-white/80 text-[9px] font-semibold"
          :class="badgeColor()"
          >{{ badge() }}</span
        >
      </div>
    </component>

    <!-- Label + row actions -->
    <div class="flex items-center gap-1 mt-1">
      <span class="flex-1 min-w-0 truncate text-xs text-slate-700" :title="label">{{ label }}</span>
      <button
        v-if="!external"
        type="button"
        class="shrink-0 opacity-0 group-hover:opacity-100 text-slate-400 hover:text-slate-600 p-0.5 rounded transition-opacity cursor-pointer"
        title="Rename"
        aria-label="Rename"
        @click="$emit('rename')"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="w-3.5 h-3.5"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M12 20h9" />
          <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
        </svg>
      </button>
      <button
        v-if="!external"
        type="button"
        class="shrink-0 opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-600 p-0.5 rounded transition-opacity cursor-pointer"
        title="Delete"
        aria-label="Delete"
        @click="$emit('delete')"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="w-3.5 h-3.5"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <polyline points="3 6 5 6 21 6" />
          <path
            d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
          />
          <line x1="10" y1="11" x2="10" y2="17" />
          <line x1="14" y1="11" x2="14" y2="17" />
        </svg>
      </button>
    </div>
  </div>
</template>
