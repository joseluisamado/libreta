import { describe, it, expect } from 'vitest'
import { Editor, Extension } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import TaskList from '@tiptap/extension-task-list'
import TaskItem from '@tiptap/extension-task-item'
import Link from '@tiptap/extension-link'
import { Table, TableRow, TableHeader, TableCell } from '@tiptap/extension-table'
import Image from '@tiptap/extension-image'
import { Markdown } from 'tiptap-markdown'
import { Plugin, PluginKey } from '@tiptap/pm/state'

// Mirror of the TableHeaderGuard defined in Editor.vue. Keep in sync.
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
          if (!headerType || !cellType) return null
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
                  const mapped = tr.mapping.map(cellPos)
                  tr = tr.setNodeMarkup(mapped, wantType, cell.attrs)
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
      StarterKit.configure({ link: false }),
      TaskList,
      TaskItem.configure({ nested: true }),
      Link.configure({ openOnClick: false, autolink: true }),
      Table.configure({ resizable: false }),
      TableRow,
      TableHeader,
      TableCell,
      TableHeaderGuard,
      Image.configure({ inline: true }),
      Markdown.configure({ html: false }),
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

    // Cursor in the header row, then delete that row — the toolbar "delete row"
    // action that originally caused the data loss.
    editor.commands.setTextSelection(3)
    editor.commands.deleteRow()

    const out = getMarkdown(editor)
    editor.destroy()

    expect(out).not.toContain('[table]')
    // The former first body row is promoted to the header row.
    expect(out).toContain('| x | y |')
    expect(out).toContain('| --- | --- |')
    expect(out).toContain('| u | v |')
  })

  it('inserting a row above the header does not collapse the table to [table]', () => {
    const editor = createEditor()
    editor.commands.setContent('| A | B |\n| --- | --- |\n| x | y |\n')

    // Cursor in the header row, then "add row before". The new plain row 0
    // pushes the old header (still header cells) down into the body — the
    // second un-serializable shape (body row containing header cells).
    editor.commands.setTextSelection(3)
    editor.commands.addRowBefore()

    const out = getMarkdown(editor)
    editor.destroy()

    expect(out).not.toContain('[table]')
    expect(out).toContain('| --- | --- |')
    // Original content survives.
    expect(out).toContain('| x | y |')
  })
})
