import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      // Playwright (`playwright.config.ts`) поднимает свой изолированный бэкенд
      // на отдельном порту, чтобы не столкнуться с уже поднятым docker-compose
      // на 8000 — `reuseExistingServer` иначе молча переиспользует его, и e2e
      // проверяет `fake`-специфичное поведение против настоящего ключа.
      '/api': {
        target: `http://localhost:${process.env.VITE_BACKEND_PORT ?? '8000'}`,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
