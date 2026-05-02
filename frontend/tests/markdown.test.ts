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
    expect(out).toContain('<pre class="hljs">')
    expect(out).toContain('language-python')
  })

  it('rewrites relative image URLs to the assets endpoint', () => {
    const out = renderMarkdown('![alt](images/foo.png)', 'recipes/lasagna')
    expect(out).toContain('/api/v1/assets/pages/recipes/images/foo.png')
  })

  it('leaves absolute image URLs alone', () => {
    const out = renderMarkdown('![alt](https://example.com/x.png)', 'recipes/lasagna')
    expect(out).toContain('https://example.com/x.png')
  })

  it('resolves ../ in image URLs', () => {
    const out = renderMarkdown('![alt](../shared/x.png)', 'recipes/lasagna')
    expect(out).toContain('/api/v1/assets/pages/shared/x.png')
  })

  it('resolves images relative to the page dir for index pages', () => {
    // Page stored as devel/concepts/saml/index.md → asset lives in saml/
    const out = renderMarkdown('![alt](foo.png)', 'devel/concepts/saml', true)
    expect(out).toContain('/api/v1/assets/pages/devel/concepts/saml/foo.png')
  })

  it('rewrites relative PDF/zip links through the assets endpoint', () => {
    const out = renderMarkdown('[doc](report.pdf)', 'housing/espana/cancer', true)
    expect(out).toContain('href="/api/v1/assets/pages/housing/espana/cancer/report.pdf"')
  })

  it('leaves wiki page links alone', () => {
    const out = renderMarkdown('[other](/w/foo/bar)', 'housing/espana/cancer', true)
    expect(out).toContain('href="/w/foo/bar"')
    expect(out).not.toContain('/api/v1/assets/')
  })

  it('leaves anchor and external links alone', () => {
    const out = renderMarkdown('[a](#x) [b](https://x.com/y.pdf)', 'foo', false)
    expect(out).toContain('href="#x"')
    expect(out).toContain('href="https://x.com/y.pdf"')
  })

  it('renders inline math', () => {
    const out = renderMarkdown('Energy $E = mc^2$ is iconic.')
    expect(out).toContain('class="katex"')
    expect(out).toContain('mathnormal') // KaTeX glyph class
  })

  it('renders block math', () => {
    const out = renderMarkdown('$$\n\\sum_{i=0}^{n} i\n$$')
    expect(out).toContain('math-block')
    expect(out).toContain('katex')
  })

  it('does not catch dollar amounts', () => {
    const out = renderMarkdown('It costs $5 and $10.')
    expect(out).not.toContain('katex')
  })
})
