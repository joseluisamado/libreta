import { describe, it, expect } from 'vitest'
import { renderMarkdown } from '@/markdown'

describe('renderMarkdown', () => {
  it('renders headings', () => {
    expect(renderMarkdown('# Hello')).toContain('<h1>Hello</h1>')
  })

  it('renders GFM tables', () => {
    const out = renderMarkdown('| a | b |\n|---|---|\n| 1 | 2 |')
    expect(out).toContain('<table>')
    expect(out).toContain('<th>a</th>')
  })

  it('strips raw HTML (P4/R6)', () => {
    const out = renderMarkdown('<script>alert(1)</script>')
    expect(out).not.toContain('<script>')
  })

  it('renders task lists', () => {
    const out = renderMarkdown('- [x] done\n- [ ] todo')
    expect(out).toContain('type="checkbox"')
  })

  it('highlights fenced code', () => {
    const out = renderMarkdown('```python\nx = 1\n```')
    expect(out).toContain('<pre>')
    expect(out).toContain('<code')
  })
})
