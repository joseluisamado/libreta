import { describe, it, expect } from 'vitest'
import { pageNameToSlug } from '@/utils/pageName'

describe('pageNameToSlug', () => {
  it('keeps underscores', () => {
    expect(pageNameToSlug('my_new_page')).toBe('my_new_page')
  })

  it('keeps hyphens and dots', () => {
    expect(pageNameToSlug('release-1.2.3')).toBe('release-1.2.3')
  })

  it('folds whitespace to a single hyphen', () => {
    expect(pageNameToSlug('My   New Page')).toBe('my-new-page')
  })

  it('lowercases', () => {
    expect(pageNameToSlug('README')).toBe('readme')
  })

  it('drops disallowed characters but keeps the rest', () => {
    expect(pageNameToSlug('hello@world!')).toBe('helloworld')
  })

  it('preserves nesting via slashes, slugging each segment', () => {
    expect(pageNameToSlug('Notes/2026/Big Idea')).toBe('notes/2026/big-idea')
  })

  it('trims stray separators from segment ends', () => {
    expect(pageNameToSlug('_hidden_')).toBe('hidden')
    expect(pageNameToSlug('-edge-')).toBe('edge')
  })

  it('drops empty segments', () => {
    expect(pageNameToSlug('a//b')).toBe('a/b')
  })

  it('returns empty string when nothing survives', () => {
    expect(pageNameToSlug('   ')).toBe('')
    expect(pageNameToSlug('@@@')).toBe('')
  })
})
