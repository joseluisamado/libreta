import { describe, it, expect } from 'vitest'
import { Editor } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import { Markdown } from 'tiptap-markdown'
import { DetailsMarkup } from '@/components/Editor/extensions/DetailsMarkup'

// The byte-identical round-trip is pinned by fixtures/details-summary.md; these
// check the document shape behind it: the tag lines become read-only atoms and
// the Markdown between them stays ordinary, editable nodes.

function load(markdown: string): Editor {
  const editor = new Editor({
    extensions: [
      StarterKit,
      DetailsMarkup,
      Image.configure({ inline: true }),
      Markdown.configure({ html: true }),
    ],
  })
  editor.commands.setContent(markdown)
  return editor
}

function getMarkdown(editor: Editor): string {
  const storage = editor.storage as unknown as Record<string, { getMarkdown: () => string }>
  return storage['markdown']?.getMarkdown() ?? ''
}

describe('DetailsMarkup', () => {
  it('turns the tag lines into atoms and keeps the body editable', () => {
    const editor = load(
      '<details name="g" open>\n<summary>S</summary>\n\n![a](a.jpg)\n\n</details>',
    )
    const types: string[] = []
    editor.state.doc.forEach((n) => types.push(n.type.name))
    // (StarterKit's trailing-node plugin may add an empty paragraph after the last atom.)
    expect(types.slice(0, 3)).toEqual(['detailsMarkup', 'paragraph', 'detailsMarkup'])
    expect(editor.state.doc.firstChild?.attrs['source']).toBe(
      '<details name="g" open>\n<summary>S</summary>',
    )
    editor.destroy()
  })

  it('survives repeated parses on the shared markdown-it instance', () => {
    const editor = load('<details>\n\nx\n\n</details>')
    editor.commands.setContent('<details open>\n\ny\n\n</details>')
    expect(getMarkdown(editor)).toBe('<details open>\n\ny\n\n</details>')
    editor.destroy()
  })

  it('does not capture a non-allow-listed opening tag as an atom', () => {
    const editor = load('<details onclick="x()">\n\nbody\n\n</details>')
    const atoms: string[] = []
    editor.state.doc.descendants((n) => {
      if (n.type.name === 'detailsMarkup') atoms.push(String(n.attrs['source']))
    })
    // Only the (allow-listed) closing line; the opening tag is not ours.
    expect(atoms).toEqual(['</details>'])
    editor.destroy()
  })

  it('keeps one-line openers, closer runs and summary tags as atoms', () => {
    const editor = load(
      '<details><summary><b>Short</b> answer</summary>\n\nx\n\n<details><summary>Long</summary>\n\ny\n\n</details></details>',
    )
    const atoms: string[] = []
    editor.state.doc.descendants((n) => {
      if (n.type.name === 'detailsMarkup') atoms.push(String(n.attrs['source']))
    })
    expect(atoms).toEqual([
      '<details><summary><b>Short</b> answer</summary>',
      '<details><summary>Long</summary>',
      '</details></details>',
    ])
    editor.destroy()
  })

  it('keeps a closer that a list runs into, adding only the blank line', () => {
    // The editor separates every pair of blocks with a blank line (its usual
    // normalization); the tag line itself comes back unchanged.
    const editor = load('<details><summary>S</summary>\n\n- one\n- two\n</details></details>')
    expect(getMarkdown(editor)).toBe(
      '<details><summary>S</summary>\n\n- one\n- two\n\n</details></details>',
    )
    editor.destroy()
  })
})
