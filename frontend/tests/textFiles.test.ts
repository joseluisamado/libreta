import { describe, it, expect } from 'vitest'
import { isImagePath, isVideoPath, isHtmlPath, isTextPath } from '@/textFiles'

describe('path classification (viewer routing)', () => {
  it('isImagePath covers common images + heic, not others', () => {
    for (const p of ['a.png', 'b.JPG', 'c.gif', 'd.svg', 'e.heic', 'f.HEIF', 'dir/g.webp']) {
      expect(isImagePath(p)).toBe(true)
    }
    for (const p of ['a.mp4', 'b.txt', 'c.html', 'd.pdf', 'noext']) {
      expect(isImagePath(p)).toBe(false)
    }
  })

  it('isVideoPath covers common video containers', () => {
    for (const p of ['a.mp4', 'b.WEBM', 'c.ogg', 'd.mov', 'e.m4v', 'dir/f.ogv']) {
      expect(isVideoPath(p)).toBe(true)
    }
    for (const p of ['a.png', 'b.txt', 'c.mp3']) {
      expect(isVideoPath(p)).toBe(false)
    }
  })

  it('isHtmlPath matches html/htm only', () => {
    expect(isHtmlPath('page.html')).toBe(true)
    expect(isHtmlPath('page.HTM')).toBe(true)
    expect(isHtmlPath('page.md')).toBe(false)
  })

  it('html is NOT treated as plain text (routes to HtmlView, not TextView)', () => {
    // isTextPath returns true for .html (it is in EXT_LANG), so routing must
    // check isHtmlPath first. This documents that ordering dependency.
    expect(isHtmlPath('x.html')).toBe(true)
  })
})
