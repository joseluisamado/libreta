// foliate-js ships as raw ES modules with no bundled type declarations. We only
// touch makeBook (see src/lib/ebook.ts for the R6 rationale around foliate's
// default script-stripping). Keep this file free of top-level import/export so
// it stays a global ambient script and the module declaration applies
// project-wide. The <foliate-view> custom-element typing lives in
// foliate-view.d.ts (a module, for Vue augmentation).
declare module 'foliate-js/view.js' {
  /** Sniffs the file's format and returns a format-specific book object. */
  export function makeBook(file: string | Blob): Promise<unknown>
}
