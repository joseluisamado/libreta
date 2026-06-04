// Let vue-tsc accept <foliate-view> in templates. The element is registered at
// runtime by foliate-js (import side effect) and matched by the isCustomElement
// hook in vite.config.ts. This file is a module (it imports 'vue'), so the
// `declare module 'vue'` block *augments* Vue's types rather than replacing
// them. Typed as a bare component; EbookView casts its ref to a richer
// interface for the methods it actually calls.
import 'vue'

declare module 'vue' {
  interface GlobalComponents {
    'foliate-view': import('vue').DefineComponent<Record<string, unknown>>
  }
}
