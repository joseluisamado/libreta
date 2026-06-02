/**
 * Display form of a git-source label.
 *
 * Sources imported from Gitea are labelled ``owner/repo`` (the repo's
 * ``full_name``). In the UI we show that as ``owner:repo`` so the ``/`` is
 * reserved for path separators only — a folder *inside* a repo and the
 * owner/repo boundary should not look alike. Purely cosmetic: the stored
 * label is left untouched.
 *
 * A label with no ``/`` (a hand-written one) is returned as-is. If a label
 * somehow contains several ``/`` we only rewrite the first, treating the rest
 * as a path-like tail.
 */
export function displaySourceLabel(label: string): string {
  const i = label.indexOf('/')
  if (i === -1) return label
  return `${label.slice(0, i)}:${label.slice(i + 1)}`
}
