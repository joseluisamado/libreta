import { createRequire } from 'node:module'
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'

// pdf.js 5.x decodes JBIG2 (scanned docs), JPEG2000, and ICC colour via wasm
// modules in `pdfjs-dist/wasm/`. pdf.js fetches them by their *literal*
// filename (e.g. `jbig2.wasm`) from a configured `wasmUrl`, so they must be
// served unhashed at a stable path. Vite's `?url` import would hash them and
// break that, so copy the directory verbatim to `/pdf-wasm/` — emitted in
// build, and served by a tiny middleware in dev. See src/lib/pdf.ts.
const PDF_WASM_BASE = '/pdf-wasm/'

function pdfWasmAssets(): Plugin {
  const require = createRequire(import.meta.url)
  const wasmDir = join(dirname(require.resolve('pdfjs-dist/package.json')), 'wasm')
  const files = readdirSync(wasmDir).filter((f) => f.endsWith('.wasm'))

  return {
    name: 'pdfjs-wasm-assets',
    // Build: emit each wasm at a fixed (unhashed) name under pdf-wasm/.
    generateBundle() {
      for (const f of files) {
        this.emitFile({
          type: 'asset',
          fileName: `pdf-wasm/${f}`,
          source: readFileSync(join(wasmDir, f)),
        })
      }
    },
    // Dev: serve the same files straight from node_modules.
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url?.startsWith(PDF_WASM_BASE)) return next()
        const name = req.url.slice(PDF_WASM_BASE.length).split('?')[0]
        if (!files.includes(name)) return next()
        res.setHeader('Content-Type', 'application/wasm')
        res.end(readFileSync(join(wasmDir, name)))
      })
    },
  }
}

const apiBase = process.env.VITE_API_BASE ?? 'http://localhost:8092'
// In docker the container listens on 5173; the host maps it to 8091.
// When running outside docker (`make dev-frontend`) we listen on 8091 directly.
const inDocker = process.env.VITE_API_BASE !== undefined
const port = inDocker ? 5173 : 8091

export default defineConfig({
  plugins: [
    // foliate-js registers a <foliate-view> web component (see EbookView);
    // tell Vue to treat it as a custom element, not a Vue component.
    vue({ template: { compilerOptions: { isCustomElement: (tag) => tag === 'foliate-view' } } }),
    pdfWasmAssets(),
  ],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    host: '0.0.0.0',
    port,
    proxy: {
      '/api': { target: apiBase, changeOrigin: true },
      '/assets': { target: apiBase, changeOrigin: true },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
  },
})
