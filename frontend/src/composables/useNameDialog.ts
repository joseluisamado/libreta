import { reactive, ref } from 'vue'

export interface NameDialogOptions {
  title: string
  label?: string
  placeholder?: string
  initial?: string
  confirmLabel?: string
  /** Show slug preview + char hint (create). When false, raw path (rename). */
  slugPreview?: boolean
}

interface NameDialogState extends Required<NameDialogOptions> {
  open: boolean
}

/**
 * Imperative, promise-based driver for {@link NameDialog}.
 *
 * Replaces `window.prompt`: call `prompt(opts)` and await the result, which is
 * the entered string, or `null` if the user cancelled. Bind `state` to the
 * `<NameDialog>` props and wire `onConfirm`/`onCancel` to its events.
 */
export function useNameDialog() {
  const state = reactive<NameDialogState>({
    open: false,
    title: '',
    label: 'Name',
    placeholder: '',
    initial: '',
    confirmLabel: 'Create',
    slugPreview: true,
  })

  const resolver = ref<((value: string | null) => void) | null>(null)

  function prompt(opts: NameDialogOptions): Promise<string | null> {
    state.title = opts.title
    state.label = opts.label ?? 'Name'
    state.placeholder = opts.placeholder ?? ''
    state.initial = opts.initial ?? ''
    state.confirmLabel = opts.confirmLabel ?? 'Create'
    state.slugPreview = opts.slugPreview ?? true
    state.open = true
    return new Promise((resolve) => {
      resolver.value = resolve
    })
  }

  function onConfirm(value: string): void {
    state.open = false
    resolver.value?.(value)
    resolver.value = null
  }

  function onCancel(): void {
    state.open = false
    resolver.value?.(null)
    resolver.value = null
  }

  return { state, prompt, onConfirm, onCancel }
}
