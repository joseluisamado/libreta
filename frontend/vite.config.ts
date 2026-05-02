import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const apiBase = process.env.VITE_API_BASE ?? 'http://localhost:8092'
// In docker the container listens on 5173; the host maps it to 8091.
// When running outside docker (`make dev-frontend`) we listen on 8091 directly.
const inDocker = process.env.VITE_API_BASE !== undefined
const port = inDocker ? 5173 : 8091

export default defineConfig({
  plugins: [vue()],
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
