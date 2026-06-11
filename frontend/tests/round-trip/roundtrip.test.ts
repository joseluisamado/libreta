import { describe, it, expect } from 'vitest'
import { Editor, Extension } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import HardBreak from '@tiptap/extension-hard-break'
import TaskList from '@tiptap/extension-task-list'
import TaskItem from '@tiptap/extension-task-item'
import Link from '@tiptap/extension-link'
import { Table, TableRow, TableHeader, TableCell } from '@tiptap/extension-table'
import Image from '@tiptap/extension-image'
import { Markdown } from 'tiptap-markdown'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import { Fragment, type Node as PMNode } from '@tiptap/pm/model'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

// Mirrors of the editor extensions in Editor.vue that affect serialization.
const MarkdownHardBreak = HardBreak.extend({
  addStorage() {
    return {
      markdown: {
        serialize(
          state: { inTable?: boolean; write: (s: string) => void },
          node: PMNode,
          parent: PMNode,
          index: number,
        ) {
          if (state.inTable) {
            state.write('<br>')
            return
          }
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
            let rowStart = pos + 1
            node.forEach((row, _rowOffset, rowIndex) => {
              const wantHeader = rowIndex === 0
              const wantType = wantHeader ? headerType : cellType
              const wantName = wantHeader ? 'tableHeader' : 'tableCell'
              let cellPos = rowStart + 1
              row.forEach((cell) => {
                if (cell.type.name !== wantName) {
                  tr = tr.setNodeMarkup(tr.mapping.map(cellPos), wantType, cell.attrs)
                  changed = true
                }
                if (cell.childCount > 1) {
                  const inline: PMNode[] = []
                  cell.forEach((block, _blockOffset, blockIndex) => {
                    if (blockIndex > 0 && hardBreakType) inline.push(hardBreakType.create())
                    block.content.forEach((leaf) => inline.push(leaf))
                  })
                  const flattened = paragraphType.create(null, Fragment.fromArray(inline))
                  const from = tr.mapping.map(cellPos + 1)
                  const to = tr.mapping.map(cellPos + cell.nodeSize - 1)
                  tr = tr.replaceWith(from, to, flattened)
                  changed = true
                }
                cellPos += cell.nodeSize
              })
              rowStart += row.nodeSize
            })
            return false
          })
          return changed ? tr : null
        },
      }),
    ]
  },
})

const FIXTURE_DIR = resolve(dirname(fileURLToPath(import.meta.url)), 'fixtures')

const fixtures = [
  'headings.md',
  'inline-formatting.md',
  'lists.md',
  'task-list.md',
  'code-block.md',
  'blockquote.md',
  'hard-breaks.md',
  'mixed.md',
  'blank-lines.md',
  'math-passthrough.md',
  'tables.md',
  'tables-cell-linebreak.md',
  'images.md',
  'file-attachments.md',
  'mermaid.md',
]

function readFixture(name: string): string {
  return readFileSync(resolve(FIXTURE_DIR, name), 'utf-8')
}

function createEditor() {
  return new Editor({
    extensions: [
      StarterKit.configure({
        // Exclude the built-in link extension so we can use our explicit
        // @tiptap/extension-link with rich link support.
        link: false,
        // Use MarkdownHardBreak so an in-cell line break serializes to `<br>`.
        hardBreak: false,
      }),
      MarkdownHardBreak,
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
      TableHeaderGuard,
      Image.configure({ inline: true }),
      Markdown.configure({
        // Match the editor: parse raw HTML so `<br>` round-trips (see Editor.vue).
        html: true,
      }),
    ],
  })
}

function normalizeTrailingNewline(s: string): string {
  // Ensure exactly one trailing newline for comparison.
  // tiptap-markdown's output may vary in trailing whitespace.
  if (!s) return '\n'
  let out = s
  while (out.endsWith('\n\n')) out = out.slice(0, -1)
  if (!out.endsWith('\n')) out += '\n'
  return out
}

/**
 * Convert a fixture to the canonical form that tiptap-markdown produces.
 * Run this once to seed the fixture files; the fixtures are then treated as
 * the authoritative stable format.
 */
function getMarkdown(editor: Editor): string {
  const storage = editor.storage as unknown as Record<string, unknown>
  const md = storage['markdown'] as { getMarkdown: () => string } | undefined
  return md?.getMarkdown() ?? ''
}

function canonicalize(markdown: string): string {
  const editor = createEditor()
  editor.commands.setContent(markdown)
  const out = getMarkdown(editor)
  editor.destroy()
  return out
}

// Set UPDATE_FIXTURES=true to regenerate all fixture files from the current
// canonical output. Only do this when the extension set changes.
const UPDATE_FIXTURES = process.env.UPDATE_FIXTURES === 'true'

describe('Markdown round-trip', () => {
  // Before tests run, optionally update fixtures to canonical form.
  // This is controlled by an env var to avoid accidental overwrites.
  if (UPDATE_FIXTURES) {
    describe('canonicalize fixtures', () => {
      for (const name of fixtures) {
        it(name, () => {
          const original = readFixture(name)
          const canonical = canonicalize(original)
          writeFileSync(resolve(FIXTURE_DIR, name), canonical, 'utf-8')
        })
      }
    })
  }

  describe('stability (single pass)', () => {
    for (const name of fixtures) {
      it(`${name} produces stable output`, () => {
        const fixture = readFixture(name)
        const pass1 = canonicalize(fixture)
        const pass2 = canonicalize(pass1)

        expect(normalizeTrailingNewline(pass2)).toBe(normalizeTrailingNewline(pass1))
      })
    }
  })

  describe('byte-identical round-trip vs canonical fixtures', () => {
    for (const name of fixtures) {
      it(name, () => {
        const fixture = readFixture(name)
        const canonical = canonicalize(fixture)

        // After canonicalization, the output must match the (already-canonical) fixture
        expect(normalizeTrailingNewline(canonical)).toBe(normalizeTrailingNewline(fixture))
      })
    }
  })
})
