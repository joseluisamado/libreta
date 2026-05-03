import { ref, watch } from 'vue'

export type ViewMode = 'rendered' | 'source'

const KEY = 'libreta:view-mode'

function load(): ViewMode {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw === 'source') return 'source'
  } catch {
    /* ignore */
  }
  return 'rendered'
}

const mode = ref<ViewMode>(load())

watch(mode, (v) => {
  try {
    localStorage.setItem(KEY, v)
  } catch {
    /* ignore */
  }
})

export function useViewMode() {
  return {
    mode,
    toggle: () => {
      mode.value = mode.value === 'rendered' ? 'source' : 'rendered'
    },
  }
}
