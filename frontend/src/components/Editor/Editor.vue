<script setup lang="ts">
  import { watch, ref, computed, nextTick, onBeforeUnmount, onMounted } from 'vue'
  import { useEditor, EditorContent } from '@tiptap/vue-3'
  import StarterKit from '@tiptap/starter-kit'
  import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight'
  import { createLowlight } from 'lowlight'
  // Use the full language set (instead of `common`) so fenced code blocks
  // with less-common languages like `nix`, `dockerfile`, `toml`, `terraform`,
  // etc. don't crash the editor on mount with "Unknown language".
  import { all } from 'lowlight'
  import TaskList from '@tiptap/extension-task-list'
  import TaskItem from '@tiptap/extension-task-item'
  import Link from '@tiptap/extension-link'
  import { Table, TableRow, TableHeader, TableCell } from '@tiptap/extension-table'
  import Image from '@tiptap/extension-image'
  import HardBreak from '@tiptap/extension-hard-break'
  import { mergeAttributes, Extension } from '@tiptap/core'
  import { Plugin, PluginKey } from '@tiptap/pm/state'
  import { Fragment, type Node as PMNode } from '@tiptap/pm/model'
  import { Decoration, DecorationSet } from '@tiptap/pm/view'
  import { Markdown } from 'tiptap-markdown'
  import 'highlight.js/styles/github.css'
  import { getClientConfig, uploadSourceAsset, upsertSourceAsset } from '@/api/client'
  import { resolveAssetUrl } from '@/markdown'
  import { getMarkdownFromStorage } from '@/markdownStorage'
  import DrawioModal from './DrawioModal.vue'
  import LinkModal from './LinkModal.vue'

  const props = defineProps<{
    content: string
    path: string
    sourceId?: string
  }>()

  const emit = defineEmits<{
    update: [markdown: string]
    'diagram-saved': []
    'editor-error': [message: string]
  }>()

  // Surfaces editor-mount / parse failures to the parent so the edit view
  // doesn't silently render a blank pane when something goes wrong (e.g. an
  // unsupported language fence or a malformed table that throws inside
  // prosemirror's schema validation).
  const editorError = ref<string | null>(null)
  function reportEditorError(scope: string, e: unknown): void {
    const msg = `${scope}: ${e instanceof Error ? e.message : String(e)}`
    editorError.value = msg
    emit('editor-error', msg)
    console.error('[libreta-editor]', scope, e)
  }

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

  // Languages offered in the per-codeblock dropdown. Keep alphabetical.
  // Any language registered with lowlight will syntax-highlight; this list
  // is just the UX shortlist of "languages a user is likely to pick".
  const CODE_LANGS: { value: string; label: string }[] = [
    { value: 'bash', label: 'bash' },
    { value: 'c', label: 'c' },
    { value: 'cpp', label: 'c++' },
    { value: 'csharp', label: 'c#' },
    { value: 'css', label: 'css' },
    { value: 'diff', label: 'diff' },
    { value: 'dockerfile', label: 'dockerfile' },
    { value: 'go', label: 'go' },
    { value: 'html', label: 'html' },
    { value: 'ini', label: 'ini' },
    { value: 'java', label: 'java' },
    { value: 'javascript', label: 'javascript' },
    { value: 'json', label: 'json' },
    { value: 'kotlin', label: 'kotlin' },
    { value: 'latex', label: 'latex' },
    { value: 'lua', label: 'lua' },
    { value: 'makefile', label: 'makefile' },
    { value: 'markdown', label: 'markdown' },
    { value: 'mermaid', label: 'mermaid' },
    { value: 'nix', label: 'nix' },
    { value: 'perl', label: 'perl' },
    { value: 'php', label: 'php' },
    { value: 'python', label: 'python' },
    { value: 'r', label: 'r' },
    { value: 'ruby', label: 'ruby' },
    { value: 'rust', label: 'rust' },
    { value: 'scss', label: 'scss' },
    { value: 'shell', label: 'shell' },
    { value: 'sql', label: 'sql' },
    { value: 'swift', label: 'swift' },
    { value: 'terraform', label: 'terraform' },
    { value: 'toml', label: 'toml' },
    { value: 'typescript', label: 'typescript' },
    { value: 'xml', label: 'xml' },
    { value: 'yaml', label: 'yaml' },
  ]

  // Per-codeblock language selector rendered as a ProseMirror widget
  // decoration anchored just before each codeBlock node. The widget is a
  // detached `<select>` whose options mirror CODE_LANGS; updating it
  // dispatches an updateAttributes transaction on the codeBlock.
  // Widget decorations live outside the editable contenteditable area, so
  // typing inside a code block does not interfere with the selector and
  // vice-versa.
  function buildLangSelect(currentLang: string, onChange: (lang: string) => void): HTMLElement {
    const wrap = document.createElement('div')
    wrap.className = 'libreta-code-lang-select'
    wrap.contentEditable = 'false'
    const select = document.createElement('select')
    select.className =
      'rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[11px] text-slate-500 hover:border-slate-400 focus:outline-none cursor-pointer'
    select.setAttribute('aria-label', 'Code block language')
    const plain = document.createElement('option')
    plain.value = ''
    plain.textContent = 'plain'
    select.appendChild(plain)
    for (const l of CODE_LANGS) {
      const opt = document.createElement('option')
      opt.value = l.value
      opt.textContent = l.label
      select.appendChild(opt)
    }
    // Selecting an option ProseMirror doesn't know about (e.g. an exotic
    // language a user typed in the markdown source) — add it dynamically so
    // the current value is reflected.
    if (currentLang && !CODE_LANGS.some((l) => l.value === currentLang)) {
      const opt = document.createElement('option')
      opt.value = currentLang
      opt.textContent = currentLang
      select.appendChild(opt)
    }
    select.value = currentLang
    select.addEventListener('change', () => {
      onChange(select.value)
    })
    // Prevent mousedown from stealing the editor selection. The change still
    // fires; we just don't want ProseMirror's selection tracker to interpret
    // the click as a doc-level event.
    select.addEventListener('mousedown', (e) => {
      e.stopPropagation()
    })
    wrap.appendChild(select)
    return wrap
  }

  const codeBlockLangSelectorKey = new PluginKey('codeBlockLangSelector')

  const CodeBlockLangSelector = Extension.create({
    name: 'codeBlockLangSelector',
    addProseMirrorPlugins() {
      return [
        new Plugin({
          key: codeBlockLangSelectorKey,
          props: {
            decorations: (state) => {
              const decorations: Decoration[] = []
              state.doc.descendants((node, pos) => {
                if (node.type.name !== 'codeBlock') return
                const lang = (node.attrs.language as string | null) ?? ''
                // Anchor at `pos` (before the codeBlock node) so the widget
                // DOM is a sibling of <pre> in the rendered output, not a
                // child of it. side: -1 keeps it ordered before the block.
                const widget = Decoration.widget(
                  pos,
                  (view) =>
                    buildLangSelect(lang, (newLang) => {
                      const tr = view.state.tr.setNodeMarkup(pos, undefined, {
                        ...node.attrs,
                        language: newLang || null,
                      })
                      view.dispatch(tr)
                    }),
                  { side: -1, ignoreSelection: true, key: `lang-${pos}-${lang}` },
                )
                decorations.push(widget)
              })
              return DecorationSet.create(state.doc, decorations)
            },
          },
        }),
      ]
    },
  })

  // A line break inside a table cell can't be a paragraph break (GFM cells are
  // single-block). The guard below rewrites such breaks into `hardBreak` nodes;
  // this extension teaches tiptap-markdown to serialize a hardBreak as a literal
  // `<br>` when it sits inside a table (the standard GFM in-cell line break).
  // Outside a table it keeps the default backslash-newline. With the editor's
  // Markdown parser set to `html: true`, the `<br>` round-trips back to a
  // hardBreak on the next load instead of re-escaping to `&lt;br&gt;`.
  const MarkdownHardBreak = HardBreak.extend({
    addStorage() {
      return {
        markdown: {
          serialize(
            state: {
              inTable?: boolean
              write: (s: string) => void
            },
            node: PMNode,
            parent: PMNode,
            index: number,
          ) {
            if (state.inTable) {
              state.write('<br>')
              return
            }
            // Default tiptap-markdown behaviour: a trailing run of hardBreaks at
            // the end of a block is dropped; otherwise emit a hard line break.
            for (let i = index + 1; i < parent.childCount; i++) {
              if (parent.child(i).type !== node.type) {
                state.write('\\\n')
                return
              }
            }
          },
          parse: {},
        },
      }
    },
  })

  // tiptap-markdown can only serialize a table that has the canonical GFM
  // shape. It falls back to the literal placeholder `[table]` — silently
  // destroying the table on save — whenever a table violates any of:
  //   1. The first row is not entirely `tableHeader` cells (no `| --- |` line).
  //   2. A later row contains a `tableHeader` cell.
  //   3. Any cell contains more than one block (e.g. two paragraphs).
  //
  // Every one of these is one edit away:
  //   • "Delete row" on the header row → header-less first row (1).
  //   • "Add row before" on the header row → header pushed into the body (2).
  //   • Pressing Enter inside a cell → a second paragraph in that cell (3).
  //
  // This guard normalizes every table after any doc change:
  //   • cell type matches row position (row 0 → header, rows 1+ → body), and
  //   • each cell is collapsed to a single paragraph, with the breaks between
  //     its former blocks preserved as `hardBreak`s (serialized to `<br>` —
  //     see MarkdownHardBreak above).
  // That makes the un-serializable shapes unreachable in persisted state and
  // doubles as the add/delete-row and in-cell-Enter UX guard.
  const tableHeaderGuardKey = new PluginKey('tableHeaderGuard')

  const TableHeaderGuard = Extension.create({
    name: 'tableHeaderGuard',
    addProseMirrorPlugins() {
      return [
        new Plugin({
          key: tableHeaderGuardKey,
          appendTransaction: (transactions, _oldState, newState) => {
            if (!transactions.some((tr) => tr.docChanged)) return null
            const headerType = newState.schema.nodes['tableHeader']
            const cellType = newState.schema.nodes['tableCell']
            const paragraphType = newState.schema.nodes['paragraph']
            const hardBreakType = newState.schema.nodes['hardBreak']
            if (!headerType || !cellType || !paragraphType) return null
            let tr = newState.tr
            let changed = false
            newState.doc.descendants((node, pos) => {
              if (node.type.name !== 'table') return
              // The first row must be all header cells; every later row must be
              // all body cells. `rowStart` walks past the table-open token
              // (pos + 1) to the first row, then accumulates each row's size.
              let rowStart = pos + 1
              node.forEach((row, _rowOffset, rowIndex) => {
                const wantHeader = rowIndex === 0
                const wantType = wantHeader ? headerType : cellType
                const wantName = wantHeader ? 'tableHeader' : 'tableCell'
                let cellPos = rowStart + 1
                row.forEach((cell) => {
                  // 1+2) Cell type must match the row's position.
                  if (cell.type.name !== wantName) {
                    // Map through edits already queued in this transaction.
                    const mapped = tr.mapping.map(cellPos)
                    tr = tr.setNodeMarkup(mapped, wantType, cell.attrs)
                    changed = true
                  }
                  // 3) A cell must hold exactly one block. Flatten extra blocks
                  // into one paragraph, joining them with hardBreaks so the
                  // line break the user typed survives as a `<br>`.
                  if (cell.childCount > 1) {
                    const inline: PMNode[] = []
                    cell.forEach((block, _blockOffset, blockIndex) => {
                      if (blockIndex > 0 && hardBreakType) {
                        inline.push(hardBreakType.create())
                      }
                      block.content.forEach((leaf) => inline.push(leaf))
                    })
                    const flattened = paragraphType.create(null, Fragment.fromArray(inline))
                    // Replace the cell's inner content (positions inside the
                    // cell, excluding the cell's open/close tokens).
                    const from = tr.mapping.map(cellPos + 1)
                    const to = tr.mapping.map(cellPos + cell.nodeSize - 1)
                    tr = tr.replaceWith(from, to, flattened)
                    changed = true
                  }
                  cellPos += cell.nodeSize
                })
                rowStart += row.nodeSize
              })
              // Don't descend into the table's rows.
              return false
            })
            return changed ? tr : null
          },
        }),
      ]
    },
  })

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
        // Exclude built-in hardBreak; we register MarkdownHardBreak below so a
        // line break inside a table cell serializes to `<br>` instead of the
        // `[hardBreak]` placeholder.
        hardBreak: false,
      }),
      MarkdownHardBreak,
      CodeBlockLowlight.configure({
        lowlight: (() => {
          const ll = createLowlight(all)
          // Belt-and-braces: the @tiptap lowlight plugin only checks
          // highlight.js's own registry — not lowlight's — before calling
          // `.highlight(lang, …)`. If a user writes a fence with an unknown
          // language, the call throws and ProseMirror's plugin init crashes,
          // unmounting the whole editor and leaving the edit page blank.
          // Wrap `.highlight` to fall back to plaintext rather than throw.
          const original = ll.highlight.bind(ll)
          ll.highlight = ((lang: string, value: string, options?: unknown) => {
            try {
              return original(lang, value, options as never)
            } catch {
              return original('plaintext', value, options as never)
            }
          }) as typeof ll.highlight
          return ll
        })(),
      }),
      CodeBlockLangSelector,
      TaskList,
      // The upstream TaskItem nodeView wires its checkbox `change` listener
      // through a chained command that captures `getPos` at dispatch time.
      // Under Vue + node-view re-renders that position is sometimes stale by
      // the time the transaction runs, producing a "RangeError: Applying a
      // mismatched transaction" and silently dropping the toggle. We replace
      // the nodeView with one that resolves the position immediately, guards
      // against an invalid lookup, and dispatches a single fresh transaction.
      TaskItem.extend({
        addNodeView() {
          return ({ node, getPos, editor: ed, HTMLAttributes }) => {
            const li = document.createElement('li')
            const label = document.createElement('label')
            const span = document.createElement('span')
            const checkbox = document.createElement('input')
            const content = document.createElement('div')
            label.contentEditable = 'false'
            checkbox.type = 'checkbox'
            checkbox.checked = node.attrs.checked === true
            li.dataset['checked'] = String(node.attrs.checked === true)
            li.dataset['type'] = 'taskItem'
            for (const [k, v] of Object.entries(HTMLAttributes || {})) {
              if (typeof v === 'string') li.setAttribute(k, v)
            }
            checkbox.addEventListener('mousedown', (e) => e.preventDefault())
            checkbox.addEventListener('change', (e) => {
              const checked = (e.target as HTMLInputElement).checked
              if (!ed.isEditable) {
                checkbox.checked = !checked
                return
              }
              const pos = typeof getPos === 'function' ? getPos() : null
              if (typeof pos !== 'number') {
                checkbox.checked = !checked
                return
              }
              const current = ed.state.doc.nodeAt(pos)
              if (!current || current.type.name !== 'taskItem') {
                checkbox.checked = !checked
                return
              }
              const tr = ed.state.tr.setNodeMarkup(pos, undefined, {
                ...current.attrs,
                checked,
              })
              ed.view.dispatch(tr)
            })
            label.append(checkbox, span)
            li.append(label, content)
            return {
              dom: li,
              contentDOM: content,
              update: (updated) => {
                if (updated.type.name !== 'taskItem') return false
                checkbox.checked = updated.attrs.checked === true
                li.dataset['checked'] = String(updated.attrs.checked === true)
                return true
              },
            }
          }
        },
      }).configure({
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
      TableHeaderGuard,
      PageScopedImage.configure({
        // Inline images live inside paragraphs (`![alt](photo.jpg)` mid-sentence).
        // Tiptap's default is block-level; switch to inline so prosemirror-markdown
        // round-trips a paragraph containing an image without splitting it.
        inline: true,
      }),
      Markdown.configure({
        // Parse raw HTML in the source so a `<br>` inside a table cell (the
        // GFM in-cell line break MarkdownHardBreak emits) round-trips back to a
        // hardBreak node instead of re-escaping to `&lt;br&gt;`. This only
        // affects the editor's client-side parser; R6's protection is the
        // render-time DOMPurify sanitization, which is unchanged.
        html: true,
      }),
    ],
    content: props.content,
    editorProps: {
      handleDoubleClickOn: (_view, _pos, node, _nodePos, event): boolean => {
        if (node.type.name !== 'image') return false
        const src = String((node.attrs as { src?: unknown }).src ?? '')
        if (!isDrawioSrc(src)) return false
        // Stop the browser's native double-click word/element selection so
        // the rendered SVG doesn't keep a highlight after the modal closes.
        event.preventDefault()
        window.getSelection()?.removeAllRanges()
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
    onCreate: ({ editor: ed }) => {
      // tiptap-markdown logs unknown nodes / parse complaints to console;
      // surface anything that left the doc empty when it shouldn't be so the
      // user sees a clear message instead of a blank editor.
      try {
        if (props.content && props.content.trim().length > 0 && ed.isEmpty) {
          reportEditorError(
            'parse',
            new Error(
              'Editor mounted but the document came out empty. ' +
                'The markdown source may contain syntax the editor cannot represent — ' +
                'switch to Source view to inspect it.',
            ),
          )
        }
      } catch (e) {
        reportEditorError('mount', e)
      }
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
      try {
        editor.value.commands.setContent(newContent)
      } catch (e) {
        reportEditorError('setContent', e)
      }
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
    if (!props.sourceId) {
      // Inline attachments live in the page's sidecar inside a git source.
      // Editing outside a source (e.g. a watched folder) has no such home.
      uploadError.value = 'Attachments are only supported when editing a git source.'
      return
    }
    try {
      const result = await uploadSourceAsset(props.sourceId, props.path, file)
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
    if (!props.sourceId) {
      drawioOpen.value = false
      uploadError.value = 'Diagrams are only supported when editing a git source.'
      return
    }
    const blob = new Blob([svg], { type: 'image/svg+xml' })
    const editingSrc = drawioEditingSrc.value
    try {
      // Upload first, while the modal is still open. This avoids racing the
      // doc mutation against focus restoration and Vue's modal teardown.
      let href: string | null = null
      if (editingSrc) {
        const filename = basenameFromSrc(editingSrc)
        await upsertSourceAsset(props.sourceId, props.path, filename, blob, 'image/svg+xml')
      } else {
        const filename = newDiagramFilename()
        const file = new File([blob], filename, { type: 'image/svg+xml' })
        const result = await uploadSourceAsset(props.sourceId, props.path, file)
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
        // The markdown didn't change (the file's bytes were replaced in
        // place at the same path), so onUpdate won't fire and the parent's
        // dirty flag won't flip on its own. Tell the parent explicitly so
        // the Save button activates.
        emit('diagram-saved')
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
    // Clear any DOM selection that may have been left over from the
    // double-click that opened the editor.
    window.getSelection()?.removeAllRanges()
  }

  // ── link dialog ───────────────────────────────────────────────────────────
  const linkOpen = ref(false)
  const linkInitialText = ref('')
  const linkInitialHref = ref('')

  function openLinkDialog(): void {
    const ed = editor.value
    if (!ed || ed.isDestroyed) return
    const { from, to } = ed.state.selection
    linkInitialText.value = from === to ? '' : ed.state.doc.textBetween(from, to, ' ')
    // If the cursor sits on an existing link, pre-fill its href so the user can
    // edit it rather than start from scratch.
    const href = ed.getAttributes('link')?.['href']
    linkInitialHref.value = typeof href === 'string' ? href : ''
    linkOpen.value = true
  }

  function onLinkSubmit(payload: { href: string; text: string }): void {
    linkOpen.value = false
    const ed = editor.value
    if (!ed || ed.isDestroyed) return
    const { from, to } = ed.state.selection
    const hadSelection = from !== to
    // Guard the re-entrant onUpdate → props.content → watcher path, matching
    // the diagram-insert flow.
    internalUpdateInFlight.value = true
    try {
      if (hadSelection) {
        // Apply the link mark across the existing selection. If the user also
        // changed the visible text, replace the selection with new linked text.
        const selectedText = ed.state.doc.textBetween(from, to, ' ')
        if (payload.text && payload.text !== selectedText) {
          ed.chain()
            .insertContentAt(
              { from, to },
              {
                type: 'text',
                text: payload.text,
                marks: [{ type: 'link', attrs: { href: payload.href } }],
              },
            )
            .run()
        } else {
          ed.chain().extendMarkRange('link').setLink({ href: payload.href }).run()
        }
      } else {
        // No selection: insert fresh linked text at the cursor.
        ed.chain()
          .insertContent({
            type: 'text',
            text: payload.text,
            marks: [{ type: 'link', attrs: { href: payload.href } }],
          })
          .run()
      }
    } finally {
      void nextTick().then(() => {
        internalUpdateInFlight.value = false
        const md = getMarkdownFromStorage(ed)
        if (md) emit('update', md)
      })
    }
  }

  function onLinkCancel(): void {
    linkOpen.value = false
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
    openLinkDialog,
  })
</script>

<template>
  <div ref="editorRoot" class="libreta-editor prose max-w-none">
    <p
      v-if="uploadError"
      class="my-2 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
    >
      Upload failed: {{ uploadError }}
    </p>
    <p
      v-if="editorError"
      class="my-2 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800"
    >
      Editor warning: {{ editorError }}
    </p>
    <EditorContent :editor="editor" />
    <DrawioModal
      v-if="drawioOpen && drawioUrl"
      :drawio-url="drawioUrl"
      :initial-xml="drawioInitialXml"
      @save="onDiagramSave"
      @cancel="onDiagramCancel"
    />
    <LinkModal
      v-if="linkOpen"
      :page-path="props.path"
      :source-id="props.sourceId"
      :initial-text="linkInitialText"
      :initial-href="linkInitialHref"
      @submit="onLinkSubmit"
      @cancel="onLinkCancel"
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
