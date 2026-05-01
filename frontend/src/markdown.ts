import MarkdownIt from 'markdown-it'
import taskLists from 'markdown-it-task-lists'
import hljs from 'highlight.js'

const md = new MarkdownIt({
  html: false, // P4/R6 — strip raw HTML at render. Save-side stripping comes with M2.
  linkify: true,
  typographer: false,
  breaks: false,
  highlight(str, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang, ignoreIllegals: true }).value
      } catch {
        /* fall through */
      }
    }
    return ''
  },
}).use(taskLists, { enabled: false, label: false })

export function renderMarkdown(source: string): string {
  return md.render(source)
}
