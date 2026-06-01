// Slug helper for page and folder *names* (distinct from the heading-anchor
// slugify in markdown.ts). The content backend (storage/paths.py) is permissive
// about path segments — it only forbids traversal, hidden, and empty segments —
// so we keep the user's intent as much as possible. Underscores in particular
// must survive: stripping them silently renames the page the user asked for.

// Characters allowed verbatim in a page-name segment. Spaces are folded to
// hyphens; everything outside this set is dropped.
export const ALLOWED_NAME_CHARS = '- _ . a–z 0–9'

/** Human-readable hint shown under the name input. */
export const NAME_HINT = 'Letters, digits, and - _ . are kept. Spaces become hyphens.'

/**
 * Normalize a page or folder name into a path-safe slug.
 *
 * Keeps lowercase letters, digits, hyphens, underscores and dots. Folds runs of
 * whitespace to a single hyphen. Leaves nesting (`/`) intact so a user can type
 * `notes/2026/ideas`. Trims stray separators from the ends of each segment.
 */
export function pageNameToSlug(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .split('/')
    .map((seg) =>
      seg
        .replace(/\s+/g, '-')
        .replace(/[^a-z0-9\-_.]/g, '')
        .replace(/^[-_.]+|[-_.]+$/g, ''),
    )
    .filter(Boolean)
    .join('/')
}
