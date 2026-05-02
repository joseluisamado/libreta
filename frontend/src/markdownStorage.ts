/**
 * Type-safe accessor for tiptap-markdown's storage.
 *
 * tiptap-markdown stores its serializer under `editor.storage.markdown`.
 * Because the package's type augmentation does not always propagate through
 * vue-tsc, this helper wraps the access with an explicit cast.
 */
import type { Editor } from '@tiptap/core'

interface MarkdownStorage {
  getMarkdown: () => string
}

export function getMarkdownFromStorage(editor: Editor): string {
  const storage = editor.storage as unknown as Record<string, unknown>
  const md = storage['markdown'] as MarkdownStorage | undefined
  return md?.getMarkdown() ?? ''
}
