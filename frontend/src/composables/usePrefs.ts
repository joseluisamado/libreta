import { ref, watch } from 'vue'

const WIDTH_KEY = 'libreta:reading-width'

type Width = 'standard' | 'wide'

function loadWidth(): Width {
  try {
    const raw = window.localStorage.getItem(WIDTH_KEY)
    if (raw === 'wide') return 'wide'
  } catch {
    /* ignore */
  }
  return 'wide'
}

const readingWidth = ref<Width>(loadWidth())

watch(readingWidth, (v) => {
  try {
    window.localStorage.setItem(WIDTH_KEY, v)
  } catch {
    /* ignore */
  }
})

export function useReadingWidth(): {
  width: typeof readingWidth
  toggle: () => void
} {
  return {
    width: readingWidth,
    toggle: () => {
      readingWidth.value = readingWidth.value === 'standard' ? 'wide' : 'standard'
    },
  }
}
