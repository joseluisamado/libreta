import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const apiBase = process.env.VITE_API_BASE ?? 'http://localhost:8080'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
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
