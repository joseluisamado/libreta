import { Node, mergeAttributes } from '@tiptap/core'
import type { Node as PMNode } from '@tiptap/pm/model'
import type MarkdownIt from 'markdown-it'
import { scanDetailsRun } from '@/lib/details'

// Keeps `<details>` / `<summary>` / `</details>` lines byte-for-byte through
// the WYSIWYG editor (R1). The editor's schema has no node for raw HTML, so
// without this tiptap-markdown would drop the tags and keep only the summary
// text, silently destroying the collapsible block on save.
//
// Each run of allow-listed tag lines (see lib/details.ts) becomes one atom
// node holding its source text, shown as a read-only chip; the Markdown
// between the opening and closing lines stays ordinary, editable blocks. On
// save the node writes its source back verbatim.

type Inst = InstanceType<typeof MarkdownIt>

const ATTR = 'data-details-markup'
const configured = new WeakSet<object>()

// tiptap-markdown calls `setup` on its shared markdown-it instance before every
// parse, so register the rule only once per instance.
function setup(md: Inst): void {
  if (configured.has(md)) return
  configured.add(md)
  md.block.ruler.before(
    'html_block',
    'details_markup',
    (state, startLine, endLine, silent) => {
      const run = scanDetailsRun(state, startLine, endLine)
      if (!run) return false
      if (silent) return true
      const token = state.push('details_markup', '', 0)
      token.block = true
      token.content = run.raw
      token.map = [startLine, run.nextLine]
      state.line = run.nextLine
      return true
    },
    { alt: ['paragraph', 'reference', 'blockquote', 'list'] },
  )
  md.renderer.rules.details_markup = (tokens, idx) =>
    `<div ${ATTR}="${md.utils.escapeHtml(tokens[idx]?.content ?? '')}"></div>\n`
}

export const DetailsMarkup = Node.create({
  name: 'detailsMarkup',
  group: 'block',
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      source: {
        default: '',
        parseHTML: (el: HTMLElement) => el.getAttribute(ATTR) ?? '',
        renderHTML: (attrs: { source?: string }) => ({ [ATTR]: attrs.source ?? '' }),
      },
    }
  },

  parseHTML() {
    return [{ tag: `div[${ATTR}]` }]
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      'div',
      mergeAttributes(HTMLAttributes, { class: 'details-markup', contenteditable: 'false' }),
      String(node.attrs['source'] ?? ''),
    ]
  },

  addStorage() {
    return {
      markdown: {
        serialize(
          state: { text: (s: string, escape?: boolean) => void; closeBlock: (n: PMNode) => void },
          node: PMNode,
        ) {
          // `text` (not `write`) so every line gets the container prefix, e.g.
          // `> ` inside a blockquote; `false` = no Markdown escaping.
          state.text(String(node.attrs['source'] ?? ''), false)
          state.closeBlock(node)
        },
        parse: { setup },
      },
    }
  },
})
