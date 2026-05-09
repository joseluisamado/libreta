import { ref, watch } from 'vue'

const WIDTH_KEY = 'libreta:reading-width'
const PDF_LAYOUT_KEY = 'libreta:pdf-layout'

type Width = 'standard' | 'wide'
type PdfLayout = 'scroll' | 'single'

function loadWidth(): Width {
  try {
    const raw = window.localStorage.getItem(WIDTH_KEY)
    if (raw === 'wide') return 'wide'
  } catch {
    /* ignore */
  }
  return 'wide'
}

function loadPdfLayout(): PdfLayout {
  try {
    const raw = window.localStorage.getItem(PDF_LAYOUT_KEY)
    if (raw === 'single') return 'single'
  } catch {
    /* ignore */
  }
  return 'scroll'
}

const readingWidth = ref<Width>(loadWidth())
const pdfLayout = ref<PdfLayout>(loadPdfLayout())

watch(readingWidth, (v) => {
  try {
    window.localStorage.setItem(WIDTH_KEY, v)
  } catch {
    /* ignore */
  }
})

watch(pdfLayout, (v) => {
  try {
    window.localStorage.setItem(PDF_LAYOUT_KEY, v)
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

export function usePdfLayout(): {
  layout: typeof pdfLayout
  toggle: () => void
} {
  return {
    layout: pdfLayout,
    toggle: () => {
      pdfLayout.value = pdfLayout.value === 'scroll' ? 'single' : 'scroll'
    },
  }
}
