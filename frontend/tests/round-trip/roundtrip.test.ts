import { describe, it, expect } from 'vitest'
import { Editor } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import TaskList from '@tiptap/extension-task-list'
import TaskItem from '@tiptap/extension-task-item'
import Link from '@tiptap/extension-link'
import { Markdown } from 'tiptap-markdown'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

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
      }),
      TaskList,
      TaskItem.configure({
        nested: true,
      }),
      Link.configure({
        openOnClick: false,
        autolink: true,
      }),
      Markdown.configure({
        html: false,
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
