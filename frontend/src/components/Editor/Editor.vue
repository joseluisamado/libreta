<script setup lang="ts">
  import { watch, ref, computed, nextTick, onBeforeUnmount, onMounted } from 'vue'
  import { useEditor, EditorContent } from '@tiptap/vue-3'
  import StarterKit from '@tiptap/starter-kit'
  import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight'
  import { createLowlight, common } from 'lowlight'
  import TaskList from '@tiptap/extension-task-list'
  import TaskItem from '@tiptap/extension-task-item'
  import Link from '@tiptap/extension-link'
  import { Table, TableRow, TableHeader, TableCell } from '@tiptap/extension-table'
  import Image from '@tiptap/extension-image'
  import { mergeAttributes } from '@tiptap/core'
  import { Markdown } from 'tiptap-markdown'
  import 'highlight.js/styles/github.css'
  import {
    getClientConfig,
    uploadAsset,
    uploadSourceAsset,
    upsertAsset,
    upsertSourceAsset,
  } from '@/api/client'
  import { resolveAssetUrl } from '@/markdown'
  import type { Editor as TiptapEditor } from '@tiptap/core'
  import { getMarkdownFromStorage } from '@/markdownStorage'
  import DrawioModal from './DrawioModal.vue'

  const props = defineProps<{
    content: string
    path: string
    sourceId?: string
  }>()

  const emit = defineEmits<{
    update: [markdown: string]
  }>()

  const hasBeenSet = ref(false)
  // True while the editor is mutating its own doc programmatically (e.g.
  // inserting a saved diagram). The props.content watcher and onUpdate must
  // not fire while this is set — the parent re-binds props.content in
  // response to onUpdate, which would re-enter the editor with a stale
  // setContent and produce "Applying a mismatched transaction".
  const internalUpdateInFlight = ref(false)

  // The Image extension stores the raw filename in `src` (`![](photo.jpg)` →
  // src="photo.jpg") so markdown round-trips byte-identically. For the editor
  // preview only, we rewrite to the asset API URL so the browser actually
  // loads the bytes.
  function isDrawioSrc(src: string): boolean {
    return /\.drawio\.svg(?:[?#]|$)/i.test(src)
  }

  const PageScopedImage = Image.extend({
    renderHTML({ HTMLAttributes }) {
      const src = String(HTMLAttributes.src ?? '')
      const display = resolveAssetUrl(src, props.path, props.sourceId)
      const extra: Record<string, string> = { src: display }
      if (isDrawioSrc(src)) {
        extra['data-drawio-src'] = src
        extra['title'] = 'Double-click to edit diagram'
      }
      return ['img', mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, extra)]
    },
  })

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
        // Exclude built-in link so we configure @tiptap/extension-link explicitly
        link: false,
        // Exclude built-in codeBlock; we use CodeBlockLowlight for syntax highlighting
        codeBlock: false,
      }),
      CodeBlockLowlight.configure({
        lowlight: createLowlight(common),
      }),
      TaskList,
      TaskItem.configure({
        nested: true,
      }),
      Link.configure({
        openOnClick: false,
        autolink: true,
      }),
      Table.configure({
        resizable: false,
      }),
      TableRow,
      TableHeader,
      TableCell,
      PageScopedImage.configure({
        // Inline images live inside paragraphs (`![alt](photo.jpg)` mid-sentence).
        // Tiptap's default is block-level; switch to inline so prosemirror-markdown
        // round-trips a paragraph containing an image without splitting it.
        inline: true,
      }),
      Markdown.configure({
        html: false,
      }),
    ],
    content: props.content,
    editorProps: {
      handleDoubleClickOn: (_view, _pos, node): boolean => {
        if (node.type.name !== 'image') return false
        const src = String((node.attrs as { src?: unknown }).src ?? '')
        if (!isDrawioSrc(src)) return false
        void openExistingDiagram(src)
        return true
      },
      handlePaste: (_view, event): boolean => {
        const items = Array.from(event.clipboardData?.items ?? [])
        const files = items
          .filter((it) => it.kind === 'file' && it.type.startsWith('image/'))
          .map((it) => it.getAsFile())
          .filter((f): f is File => f !== null)
        if (files.length === 0) return false
        event.preventDefault()
        for (const f of files) void uploadAndInsert(f)
        return true
      },
    },
    onUpdate: () => {
      if (!hasBeenSet.value) return
      if (!editor.value || editor.value.isDestroyed) return
      // Suppress while we're applying a diagram-save mutation. The parent's
      // update handler re-binds props.content, which lands back in our
      // props.content watcher and dispatches setContent — racing with the
      // insertContent transaction we're still in the middle of applying.
      if (internalUpdateInFlight.value) return
      const md = getMarkdownFromStorage(editor.value)
      if (md) {
        emit('update', md)
      }
    },
  })

  // Watch for page navigation: load new content without marking dirty.
  // Skip when the incoming content matches the editor's current markdown —
  // the parent re-emits `props.content` after every onUpdate; calling
  // setContent on an already-equal doc jumps the caret to the start and can
  // race with in-flight transactions.
  watch(
    () => props.content,
    (newContent) => {
      if (!editor.value || editor.value.isDestroyed) return
      if (internalUpdateInFlight.value) return
      const current = getMarkdownFromStorage(editor.value)
      if (current === newContent) return
      hasBeenSet.value = false
      editor.value.commands.setContent(newContent)
      // Mark as set after a tick so that onUpdate does not fire for the initial load
      requestAnimationFrame(() => {
        hasBeenSet.value = true
      })
    },
  )

  // After initial mount, mark as set
  watch(
    editor,
    (ed) => {
      if (ed) {
        requestAnimationFrame(() => {
          hasBeenSet.value = true
        })
      }
    },
    { immediate: true },
  )

  onBeforeUnmount(() => {
    editor.value?.destroy()
  })

  const CODE_LANGS = [
    { value: 'bash', label: 'bash' },
    { value: 'c', label: 'c' },
    { value: 'cpp', label: 'c++' },
    { value: 'css', label: 'css' },
    { value: 'diff', label: 'diff' },
    { value: 'go', label: 'go' },
    { value: 'html', label: 'html' },
    { value: 'java', label: 'java' },
    { value: 'javascript', label: 'javascript' },
    { value: 'json', label: 'json' },
    { value: 'kotlin', label: 'kotlin' },
    { value: 'markdown', label: 'markdown' },
    { value: 'mermaid', label: 'mermaid' },
    { value: 'python', label: 'python' },
    { value: 'ruby', label: 'ruby' },
    { value: 'rust', label: 'rust' },
    { value: 'sql', label: 'sql' },
    { value: 'swift', label: 'swift' },
    { value: 'toml', label: 'toml' },
    { value: 'typescript', label: 'typescript' },
    { value: 'xml', label: 'xml' },
    { value: 'yaml', label: 'yaml' },
  ]

  const activeCodeBlockLang = computed(() => {
    if (!editor.value?.isActive('codeBlock')) return ''
    return (editor.value.getAttributes('codeBlock').language as string | undefined) ?? ''
  })

  function setCodeBlockLang(lang: string): void {
    if (!editor.value || editor.value.isDestroyed) return
    editor.value
      .chain()
      .focus()
      .updateAttributes('codeBlock', { language: lang || null })
      .run()
  }

  const editorRoot = ref<HTMLDivElement | null>(null)

  // While the editor is mounted (i.e. the user is on the edit page), accept
  // file drops anywhere in the window. This avoids the trap where the user
  // drops on whitespace just outside the editor's content box (still inside
  // the edit-view scroll container) and the browser navigates instead.
  function editorMounted(): boolean {
    return editorRoot.value !== null
  }

  function onWindowDragOver(event: DragEvent): void {
    if (!editorMounted()) return
    if (!(event.dataTransfer?.types ?? []).includes('Files')) return
    event.preventDefault()
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
  }

  function onWindowDrop(event: DragEvent): void {
    if (!editorMounted()) return
    // Always prevent default while on the edit page — even if there's no file
    // payload, navigating away would lose the user's edits.
    event.preventDefault()
    event.stopPropagation()
    const files = Array.from(event.dataTransfer?.files ?? [])
    for (const f of files) void uploadAndInsert(f)
  }

  // Attach to window in capture phase: guaranteed to run before any element-
  // level listener inside the editor (including ProseMirror's). The
  // eventInsideEditor() guard scopes the behavior to drops on our editor area.
  onMounted(() => {
    window.addEventListener('dragover', onWindowDragOver, true)
    window.addEventListener('drop', onWindowDrop, true)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('dragover', onWindowDragOver, true)
    window.removeEventListener('drop', onWindowDrop, true)
  })

  const uploadError = ref<string | null>(null)

  async function uploadAndInsert(file: File): Promise<void> {
    if (!editor.value || editor.value.isDestroyed) return
    uploadError.value = null
    try {
      const result = props.sourceId
        ? await uploadSourceAsset(props.sourceId, props.path, file)
        : await uploadAsset(props.path, file)
      const ed = editor.value
      // Markdown link destinations cannot contain literal spaces (CommonMark
      // spec).  Encode each path segment so the serialized markdown is valid.
      const href = result.filename.split('/').map(encodeURIComponent).join('/')
      if (result.kind === 'image') {
        const alt = file.name.replace(/\.[^.]+$/, '')
        ed.chain().focus().setImage({ src: href, alt }).run()
      } else {
        // Insert as a markdown-style link: the visible text is the filename,
        // the href is the same filename (relative to the page), so it
        // serializes to `[filename](filename)` and round-trips cleanly.
        ed.chain()
          .focus()
          .insertContent({
            type: 'text',
            text: result.filename,
            marks: [{ type: 'link', attrs: { href } }],
          })
          .run()
      }
    } catch (e) {
      uploadError.value = e instanceof Error ? e.message : String(e)
    }
  }

  // ── diagrams.net integration ──────────────────────────────────────────
  const drawioUrl = ref<string | null>(null)
  const drawioOpen = ref(false)
  const drawioInitialXml = ref<string>('')
  // The src as it appears in markdown (e.g. ".page.md/diagram.drawio.svg").
  // null when inserting a new diagram.
  const drawioEditingSrc = ref<string | null>(null)

  void getClientConfig()
    .then((cfg) => {
      drawioUrl.value = cfg.drawio_url
    })
    .catch(() => {
      drawioUrl.value = null
    })

  function newDiagramFilename(): string {
    const ts = new Date()
    const pad = (n: number): string => String(n).padStart(2, '0')
    const stamp =
      `${ts.getFullYear()}${pad(ts.getMonth() + 1)}${pad(ts.getDate())}` +
      `-${pad(ts.getHours())}${pad(ts.getMinutes())}${pad(ts.getSeconds())}`
    return `diagram-${stamp}.drawio.svg`
  }

  function basenameFromSrc(src: string): string {
    const clean = src.split('?')[0]?.split('#')[0] ?? src
    const parts = clean.split('/')
    return parts[parts.length - 1] ?? clean
  }

  function extractEditableXml(svgText: string): string {
    // drawio's xmlsvg export stores the editable graph in the root <svg>'s
    // `content` attribute (mxfile XML). If that's missing, drawio can still
    // open the SVG and recover something, so falling back to '' is safe.
    const m = svgText.match(/<svg[^>]*\scontent="([^"]*)"/i)
    if (!m || !m[1]) return ''
    const decoded = m[1]
      .replace(/&quot;/g, '"')
      .replace(/&apos;/g, "'")
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&amp;/g, '&')
    return decoded
  }

  function openInsertDiagram(): void {
    if (!drawioUrl.value) {
      uploadError.value = 'Diagram editor URL not configured'
      return
    }
    drawioEditingSrc.value = null
    drawioInitialXml.value = ''
    drawioOpen.value = true
  }

  async function openExistingDiagram(markdownSrc: string): Promise<void> {
    if (!drawioUrl.value) return
    const url = resolveAssetUrl(markdownSrc, props.path, props.sourceId)
    try {
      const r = await fetch(url)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const svg = await r.text()
      drawioInitialXml.value = extractEditableXml(svg)
      drawioEditingSrc.value = markdownSrc
      drawioOpen.value = true
    } catch (e) {
      uploadError.value = `Could not load diagram: ${e instanceof Error ? e.message : String(e)}`
    }
  }

  function bustImgCache(markdownSrc: string): void {
    // The doc's image src is unchanged (we replaced the file bytes in place),
    // so ProseMirror won't re-render the <img>. Tell the browser to refetch
    // by appending a cache-busting query to the rendered <img>'s src — the
    // canonical src on the prosemirror node is left alone so the markdown
    // round-trip stays byte-identical.
    const root = editorRoot.value
    if (!root) return
    const resolved = resolveAssetUrl(markdownSrc, props.path, props.sourceId)
    const imgs = root.querySelectorAll<HTMLImageElement>('img')
    imgs.forEach((img) => {
      // Compare the path part — `img.src` is absolute, `resolved` may be
      // relative depending on the dev/prod base URL.
      try {
        const a = new URL(img.src, window.location.origin)
        const b = new URL(resolved, window.location.origin)
        if (a.pathname === b.pathname) {
          img.src = `${b.pathname}?v=${Date.now()}`
        }
      } catch {
        // ignore malformed URLs
      }
    })
  }

  async function onDiagramSave(svg: string): Promise<void> {
    uploadError.value = null
    const blob = new Blob([svg], { type: 'image/svg+xml' })
    const editingSrc = drawioEditingSrc.value
    try {
      // Upload first, while the modal is still open. This avoids racing the
      // doc mutation against focus restoration and Vue's modal teardown.
      let href: string | null = null
      if (editingSrc) {
        const filename = basenameFromSrc(editingSrc)
        if (props.sourceId) {
          await upsertSourceAsset(props.sourceId, props.path, filename, blob, 'image/svg+xml')
        } else {
          await upsertAsset(props.path, filename, blob, 'image/svg+xml')
        }
      } else {
        const filename = newDiagramFilename()
        const file = new File([blob], filename, { type: 'image/svg+xml' })
        const result = props.sourceId
          ? await uploadSourceAsset(props.sourceId, props.path, file)
          : await uploadAsset(props.path, file)
        href = result.filename.split('/').map(encodeURIComponent).join('/')
      }

      // Close the modal and let Vue tear it down + return focus to the
      // editor before we mutate the prosemirror doc. nextTick + a follow-up
      // microtask flush makes sure the focus-induced selection transaction
      // has been dispatched before our own runs — otherwise our tx's `before`
      // doc doesn't match `state.doc` and ProseMirror throws "mismatched
      // transaction".
      drawioOpen.value = false
      await nextTick()
      await Promise.resolve()

      const ed = editor.value
      if (!ed || ed.isDestroyed) return

      if (editingSrc) {
        bustImgCache(editingSrc)
      } else if (href) {
        // Don't call focus() here: Tiptap's focus dispatches a selection
        // transaction which fans out to onUpdate → parent → props.content →
        // our watcher. That re-entry races with insertContent and trips
        // "mismatched transaction". The user's pointer is on the page; the
        // diagram inserts at the cursor and they keep typing if they want.
        internalUpdateInFlight.value = true
        try {
          ed.commands.insertContent({
            type: 'image',
            attrs: { src: href, alt: 'diagram' },
          })
        } finally {
          // Emit a single, post-tick update so the parent learns about the
          // new doc state once, after all transactions have settled.
          await nextTick()
          internalUpdateInFlight.value = false
          const md = getMarkdownFromStorage(ed)
          if (md) emit('update', md)
        }
      }
    } catch (e) {
      drawioOpen.value = false
      uploadError.value = e instanceof Error ? e.message : String(e)
    }
  }

  function onDiagramCancel(): void {
    drawioOpen.value = false
  }

  function getMarkdown(): string {
    if (!editor.value || editor.value.isDestroyed) return props.content
    return getMarkdownFromStorage(editor.value) || props.content
  }

  const editorInstance = computed(() => editor.value ?? null)

  defineExpose({
    getMarkdown,
    editor: editorInstance,
    uploadAndInsert,
    openInsertDiagram,
  })
</script>

<template>
  <div ref="editorRoot" class="libreta-editor prose max-w-none">
    <div
      v-if="editor && editor.isActive('codeBlock')"
      class="code-lang-float mb-1 flex items-center gap-1"
    >
      <span class="text-[10px] text-slate-400">language:</span>
      <select
        :value="activeCodeBlockLang"
        class="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[11px] text-slate-600 hover:border-slate-400 focus:outline-none"
        @change="setCodeBlockLang(($event.target as HTMLSelectElement).value)"
      >
        <option value="">plain</option>
        <option v-for="l in CODE_LANGS" :key="l.value" :value="l.value">{{ l.label }}</option>
      </select>
    </div>
    <p
      v-if="uploadError"
      class="my-2 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
    >
      Upload failed: {{ uploadError }}
    </p>
    <EditorContent :editor="editor" />
    <DrawioModal
      v-if="drawioOpen && drawioUrl"
      :drawio-url="drawioUrl"
      :initial-xml="drawioInitialXml"
      @save="onDiagramSave"
      @cancel="onDiagramCancel"
    />
  </div>
</template>

<style scoped>
  .libreta-editor :deep(.ProseMirror) {
    min-height: 20rem;
    outline: none;
    padding: 0;
  }

  .libreta-editor :deep(.ProseMirror p.is-editor-empty:first-child::before) {
    content: attr(data-placeholder);
    float: left;
    color: #94a3b8;
    pointer-events: none;
    height: 0;
  }

  .libreta-editor :deep(h1) {
    font-size: 1.875rem;
    font-weight: 700;
    margin-top: 1.5rem;
    margin-bottom: 0.5rem;
  }

  .libreta-editor :deep(h2) {
    font-size: 1.5rem;
    font-weight: 600;
    margin-top: 1.25rem;
    margin-bottom: 0.5rem;
  }

  .libreta-editor :deep(h3) {
    font-size: 1.25rem;
    font-weight: 600;
    margin-top: 1rem;
    margin-bottom: 0.5rem;
  }

  .libreta-editor :deep(p) {
    margin-top: 0.5rem;
    margin-bottom: 0.5rem;
  }

  .libreta-editor :deep(ul),
  .libreta-editor :deep(ol) {
    padding-left: 1.5rem;
  }

  .libreta-editor :deep(blockquote) {
    border-left: 3px solid #e2e8f0;
    padding-left: 1rem;
    color: #475569;
  }

  .libreta-editor :deep(pre) {
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 0.375rem;
    padding: 0.75rem 1rem;
    overflow-x: auto;
  }

  .libreta-editor :deep(code) {
    background-color: #f1f5f9;
    border-radius: 0.25rem;
    padding: 0.125rem 0.25rem;
    font-size: 0.875em;
  }

  .libreta-editor :deep(pre code) {
    background-color: transparent;
    padding: 0;
  }

  .libreta-editor :deep(hr) {
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 1.5rem 0;
  }

  .libreta-editor :deep(a) {
    color: #2563eb;
    text-decoration: underline;
  }

  .libreta-editor :deep(s) {
    text-decoration: line-through;
  }

  .libreta-editor :deep(ul[data-type='taskList']) {
    list-style: none;
    padding-left: 0;
  }

  .libreta-editor :deep(ul[data-type='taskList'] li) {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .libreta-editor :deep(ul[data-type='taskList'] li label) {
    margin-top: 0.25rem;
  }

  .libreta-editor :deep(table) {
    border-collapse: collapse;
    margin: 0.75rem 0;
    width: auto;
    table-layout: fixed;
    overflow: hidden;
  }

  .libreta-editor :deep(table td),
  .libreta-editor :deep(table th) {
    border: 1px solid #cbd5e1;
    padding: 0.4rem 0.6rem;
    vertical-align: top;
    min-width: 4rem;
  }

  .libreta-editor :deep(table th) {
    background-color: #f1f5f9;
    font-weight: 600;
    text-align: left;
  }

  .libreta-editor :deep(.tableWrapper) {
    overflow-x: auto;
  }

  .libreta-editor :deep(.selectedCell::after) {
    content: '';
    position: absolute;
    inset: 0;
    background: rgba(37, 99, 235, 0.12);
    pointer-events: none;
  }

  .libreta-editor :deep(table .selectedCell) {
    position: relative;
  }

  .libreta-editor :deep(img) {
    max-width: 100%;
    height: auto;
    border-radius: 0.25rem;
  }

  .libreta-editor :deep(img.ProseMirror-selectednode) {
    outline: 2px solid #2563eb;
  }
</style>
