<script setup lang="ts">
  import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
  import { pdfjs, PDF_DOC_OPTIONS } from '@/lib/pdf'
  import { coverObjectUrl } from '@/lib/ebook'
  import { renderMarkdown, renderMermaidIn } from '@/markdown'
  import { sanitizeHtmlFile } from '@/lib/html'
  import { EXT_LANG } from '@/textFiles'
  import hljs from 'highlight.js'
  import 'highlight.js/styles/github.css'

  // First-page PDF thumbnails, cached as data URLs keyed by raw URL and shared
  // across every tile for the session (module scope, not per-instance), so
  // re-entering a folder / toggling view / resizing skips the re-parse.
  const pdfThumbCache = new Map<string, string>()

  // E-book cover thumbnails, cached as object URLs keyed by raw URL, shared
  // across tiles for the session (same rationale as pdfThumbCache). The value
  // is `null` for books that have no cover, so we don't re-unzip them on every
  // re-render just to rediscover the absence.
  const ebookCoverCache = new Map<string, string | null>()

  // A tile in the preview grid. Renders a self-generated preview of the file
  // content — rendered markdown for pages, the first page of a PDF drawn to a
  // canvas (no native viewer chrome), the image itself, a raw snippet for
  // plain text — with the filename below. Clicking navigates (RouterLink) or
  // downloads (plain <a>) depending on `external`.
  type TileKind =
    | 'folder'
    | 'pdf'
    | 'page'
    | 'image'
    | 'drawio'
    | 'html'
    | 'text'
    | 'video'
    | 'ebook'
    | 'binary'

  const props = defineProps<{
    to: string
    label: string
    kind: TileKind
    size: number
    rawUrl?: string
    // Page path + source context, so relative asset links (images,
    // .drawio.svg) inside a markdown thumbnail resolve to the same /assets
    // URL the full viewer uses. Only meaningful for kind === 'page'.
    pagePath?: string
    sourceId?: string
    watchedLabel?: string
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

  // Trim already-sanitized HTML to ~max chars for a small thumbnail DOM,
  // cutting back to the last complete tag so we never leave a half-open
  // `<div cla\u2026` fragment. The browser auto-closes any elements left open by
  // the cut, and the tile's overflow-hidden box clips what's off-screen.
  function trimHtml(html: string, max: number): string {
    const slice = html.slice(0, max)
    const lastClose = slice.lastIndexOf('>')
    return lastClose === -1 ? slice : slice.slice(0, lastClose + 1)
  }

  const renderedHtml = ref<string>('')
  const rawSnippet = ref<string>('')
  const previewError = ref(false)
  const loading = ref(false)

  // page → rendered markdown HTML; text → raw monospace snippet.
  const isMarkdown = computed(() => props.kind === 'page')
  const isHtml = computed(() => props.kind === 'html')
  const isText = computed(() => props.kind === 'text')
  // A .drawio.svg *is* an SVG file — render it natively like any image,
  // matching the full viewer, instead of falling back to a badge.
  const isImage = computed(() => props.kind === 'image' || props.kind === 'drawio')
  const isPdf = computed(() => props.kind === 'pdf')
  const isVideo = computed(() => props.kind === 'video')
  const isEbook = computed(() => props.kind === 'ebook')
  const isFolder = computed(() => props.kind === 'folder')

  // Container for the rendered markdown, so we can run mermaid inside it.
  const mdEl = ref<HTMLElement | null>(null)

  // Syntax-highlight the text snippet the same way the full viewer (TextView)
  // does: map the file extension to a hljs language, fall back to auto-detect.
  const textLang = computed(() => {
    const name = props.label.toLowerCase()
    if (name === 'dockerfile') return 'dockerfile'
    if (name === 'makefile') return 'makefile'
    const dot = name.lastIndexOf('.')
    const ext = dot === -1 ? '' : name.slice(dot + 1)
    const cand = ext ? EXT_LANG[ext] : undefined
    return cand && hljs.getLanguage(cand) ? cand : ''
  })

  const highlightedSnippet = computed(() => {
    if (!rawSnippet.value) return ''
    return textLang.value
      ? hljs.highlight(rawSnippet.value, { language: textLang.value }).value
      : hljs.highlightAuto(rawSnippet.value).value
  })

  async function loadTextual(): Promise<void> {
    if (!props.rawUrl || (!isMarkdown.value && !isText.value && !isHtml.value)) return
    loading.value = true
    previewError.value = false
    try {
      const r = await fetch(props.rawUrl)
      if (!r.ok) throw new Error(String(r.status))
      const full = await r.text()
      if (isMarkdown.value) {
        // Strip frontmatter first so it doesn't eat the snippet budget, then
        // render. Pass page/source context so relative asset links (images,
        // .drawio.svg) resolve to the same /assets URL as the full viewer.
        // We only render the first ~SNIPPET_CHARS, so embedded assets past the
        // first page never enter the DOM — no fetch storm.
        renderedHtml.value = renderMarkdown(
          stripFrontmatter(full).slice(0, SNIPPET_CHARS),
          props.pagePath ?? '',
          props.sourceId,
          props.watchedLabel,
        )
        // Run mermaid only when the snippet actually contains a diagram, so a
        // grid of plain-prose tiles pays nothing.
        if (renderedHtml.value.includes('class="mermaid"')) {
          await nextTick()
          if (mdEl.value) await renderMermaidIn(mdEl.value)
        }
      } else if (isHtml.value) {
        // Render the HTML file with JS stripped (R6), artifacts rerooted to
        // the source's /assets endpoint. Unlike markdown we must NOT slice the
        // raw text first: an HTML file's first thousands of chars are <head>
        // boilerplate (a "Save Page As" doc puts <body> well past 4 KB), so a
        // raw slice yields head-only → empty body → blank tile. Sanitize the
        // whole document (DOMPurify drops <head>/<script> and returns the
        // body), then trim the *result* to keep the per-tile DOM small; the
        // tile's overflow-hidden box clips the rest visually.
        const clean = sanitizeHtmlFile(full, {
          pagePath: props.pagePath ?? '',
          sourceId: props.sourceId,
          watchedLabel: props.watchedLabel,
          // Drop head leftovers (title/link/style) so the snippet budget
          // reaches visible body content instead of <link> soup.
          bodyOnly: true,
        })
        renderedHtml.value = clean.length > SNIPPET_CHARS ? trimHtml(clean, SNIPPET_CHARS) : clean
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

  // ── E-book cover render ──────────────────────────────────────────────────
  //
  // foliate-js unzips the book client-side and exposes its cover via
  // book.getCover() (a Blob). We turn it into an object URL, cached at module
  // scope (ebookCoverCache) so re-entering a folder or toggling views skips the
  // re-parse. Books with no cover cache `null` and fall back to the badge.
  const ebookCover = ref<string>('')

  async function loadEbook(): Promise<void> {
    if (!props.rawUrl || !isEbook.value) return
    const url = props.rawUrl
    const myToken = ++renderToken

    if (ebookCoverCache.has(url)) {
      ebookCover.value = ebookCoverCache.get(url) ?? ''
      loading.value = false
      previewError.value = false
      return
    }

    loading.value = true
    previewError.value = false
    try {
      const objUrl = await coverObjectUrl(url)
      if (myToken !== renderToken) {
        if (objUrl) URL.revokeObjectURL(objUrl)
        return
      }
      ebookCoverCache.set(url, objUrl)
      ebookCover.value = objUrl ?? ''
    } catch {
      if (myToken === renderToken) previewError.value = true
    } finally {
      if (myToken === renderToken) loading.value = false
    }
  }

  watch(
    () => [props.rawUrl, props.kind] as const,
    () => {
      renderedHtml.value = ''
      rawSnippet.value = ''
      pdfThumbnail.value = ''
      ebookCover.value = ''
      void loadTextual()
      void loadPdf()
      void loadEbook()
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
      case 'html':
        return 'HTML'
      case 'text':
        return 'TXT'
      case 'video':
        return 'VID'
      case 'ebook':
        return 'BOOK'
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
      case 'html':
        return 'text-amber-600'
      case 'text':
        return 'text-violet-500'
      case 'video':
        return 'text-fuchsia-500'
      case 'ebook':
        return 'text-teal-500'
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

        <!-- Video: first frame as a poster. preload="metadata" makes the
             browser paint frame 0 with no JS; #t=0.1 nudges it to actually
             show a frame on browsers that won't paint t=0. No controls and
             pointer-events-none so a click falls through to the tile link
             (→ viewer), consistent with every other kind. -->
        <video
          v-else-if="isVideo && rawUrl"
          :key="rawUrl"
          :src="`${rawUrl}#t=0.1`"
          preload="metadata"
          muted
          playsinline
          class="w-full h-full object-cover bg-black pointer-events-none"
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

        <!-- E-book cover (extracted by foliate-js), cached. Books with no
             cover fall back to the BOOK badge. -->
        <template v-else-if="isEbook">
          <div v-if="loading && !ebookCover" class="text-[11px] text-slate-400">Loading…</div>
          <img
            v-else-if="ebookCover"
            :src="ebookCover"
            :alt="label"
            class="w-full h-full object-contain bg-white"
          />
          <span v-else class="text-2xl font-bold" :class="badgeColor()">{{ badge() }}</span>
        </template>

        <!-- Rendered markdown / HTML thumbnail (both produce renderedHtml) -->
        <template v-else-if="isMarkdown || isHtml">
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
            <div ref="mdEl" class="prose prose-sm p-3" v-html="renderedHtml" />
          </div>
        </template>

        <!-- Syntax-highlighted text snippet (same colours as TextView) -->
        <template v-else-if="isText">
          <div v-if="loading" class="text-[11px] text-slate-400">Loading…</div>
          <!-- eslint-disable-next-line vue/no-v-html -->
          <pre
            v-else-if="rawSnippet"
            class="hljs w-full h-full overflow-hidden p-2 text-[9px] leading-snug whitespace-pre-wrap break-words"
          ><code :class="textLang ? `language-${textLang}` : ''" v-html="highlightedSnippet"
          /></pre>
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
