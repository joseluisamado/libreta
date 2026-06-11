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

// Mirror of the TableHeaderGuard defined in Editor.vue.
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
          if (!headerType) return null
          let tr = newState.tr
          let changed = false
          newState.doc.descendants((node, pos) => {
            if (node.type.name !== 'table') return
            const firstRow = node.firstChild
            if (!firstRow) return
            let cellPos = pos + 2
            firstRow.forEach((cell) => {
              if (cell.type.name === 'tableCell') {
                const mapped = tr.mapping.map(cellPos)
                tr = tr.setNodeMarkup(mapped, headerType, cell.attrs)
                changed = true
              }
              cellPos += cell.nodeSize
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

    // Put the cursor inside the first (header) row and delete that row,
    // reproducing the toolbar "delete row" action that caused the data loss.
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
})
