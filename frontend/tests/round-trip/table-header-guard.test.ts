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

// Mirrors of the editor extensions defined in Editor.vue. Keep in sync.

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

function createEditor() {
  return new Editor({
    extensions: [
      StarterKit.configure({ link: false, hardBreak: false }),
      MarkdownHardBreak,
      TaskList,
      TaskItem.configure({ nested: true }),
      Link.configure({ openOnClick: false, autolink: true }),
      Table.configure({ resizable: false }),
      TableRow,
      TableHeader,
      TableCell,
      TableHeaderGuard,
      Image.configure({ inline: true }),
      Markdown.configure({ html: true }),
    ],
  })
}

function getMarkdown(editor: Editor): string {
  const storage = editor.storage as unknown as Record<string, unknown>
  const md = storage['markdown'] as { getMarkdown: () => string } | undefined
  return md?.getMarkdown() ?? ''
}

describe('table header guard', () => {
  it('deleting the header row does not collapse the table to [table]', () => {
    const editor = createEditor()
    editor.commands.setContent('| A | B |\n| --- | --- |\n| x | y |\n| u | v |\n')

    editor.commands.setTextSelection(3)
    editor.commands.deleteRow()

    const out = getMarkdown(editor)
    editor.destroy()

    expect(out).not.toContain('[table]')
    expect(out).toContain('| x | y |')
    expect(out).toContain('| --- | --- |')
    expect(out).toContain('| u | v |')
  })

  it('inserting a row above the header does not collapse the table to [table]', () => {
    const editor = createEditor()
    editor.commands.setContent('| A | B |\n| --- | --- |\n| x | y |\n')

    editor.commands.setTextSelection(3)
    editor.commands.addRowBefore()

    const out = getMarkdown(editor)
    editor.destroy()

    expect(out).not.toContain('[table]')
    expect(out).toContain('| --- | --- |')
    expect(out).toContain('| x | y |')
  })

  it('a multi-paragraph cell flattens to one line joined by <br>', () => {
    const editor = createEditor()
    // A body cell holding two paragraphs — the shape produced by pressing
    // Enter inside a cell. Build it directly to avoid relying on key handling.
    editor.commands.setContent({
      type: 'doc',
      content: [
        {
          type: 'table',
          content: [
            {
              type: 'tableRow',
              content: [
                {
                  type: 'tableHeader',
                  content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Field' }] }],
                },
                {
                  type: 'tableHeader',
                  content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Value' }] }],
                },
              ],
            },
            {
              type: 'tableRow',
              content: [
                {
                  type: 'tableCell',
                  content: [{ type: 'paragraph', content: [{ type: 'text', text: 'RAM' }] }],
                },
                {
                  type: 'tableCell',
                  content: [
                    {
                      type: 'paragraph',
                      content: [{ type: 'text', text: '32 GB', marks: [{ type: 'bold' }] }],
                    },
                    { type: 'paragraph', content: [{ type: 'text', text: '16 GB Crucial' }] },
                  ],
                },
              ],
            },
          ],
        },
      ],
    })

    const out = getMarkdown(editor)
    editor.destroy()

    expect(out).not.toContain('[table]')
    expect(out).toContain('**32 GB**<br>16 GB Crucial')

    // And the produced markdown must round-trip stably (no &lt;br&gt; escape).
    const editor2 = createEditor()
    editor2.commands.setContent(out)
    const out2 = getMarkdown(editor2)
    editor2.destroy()
    expect(out2).not.toContain('[table]')
    expect(out2).not.toContain('&lt;br&gt;')
    expect(out2).toBe(out)
  })
})
