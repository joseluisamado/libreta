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
})
