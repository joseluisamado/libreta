// Centralised pdf.js setup so the full viewer (PdfView) and the folder
// thumbnails (PreviewTile) share identical configuration and can't drift.
//
// Besides the worker, pdf.js 5.x decodes JBIG2 (scanned B/W documents),
// JPEG2000, and ICC colour via separate WebAssembly modules. Without a valid
// `wasmUrl` pointing at those files, image-only/scanned PDFs parse (the page
// count is right) but every page renders blank with "JBig2 failed to
// initialize". Vector/text PDFs need no wasm, which is why the failure is
// file-specific.
//
// pdf.js fetches each wasm by its literal filename (e.g. `jbig2.wasm`) from
// `wasmUrl`, so the files must be served unhashed at a stable path. The
// `pdfjs-wasm-assets` plugin in vite.config.ts copies them to `/pdf-wasm/`
// (emitted in build, served from node_modules in dev).
import * as pdfjs from 'pdfjs-dist/legacy/build/pdf.mjs'
import workerUrl from 'pdfjs-dist/legacy/build/pdf.worker.mjs?url'

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

// Shared loader options. Trailing slash matters — pdf.js appends the bare
// filename directly to this base.
export const PDF_DOC_OPTIONS = {
  wasmUrl: '/pdf-wasm/',
} as const

export { pdfjs }
