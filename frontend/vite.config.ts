import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const backend = process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'

const proxyPaths = [
  '/login',
  '/logout',
  '/register',
  '/upload-image',
  '/create',
  '/personal',
  '/delete',
  '/uploads',
  '/health',
]

const proxy = Object.fromEntries(
  proxyPaths.map((p) => [
    p,
    {
      target: backend,
      changeOrigin: true,
    },
  ]),
)

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 43173,
    strictPort: true,
    proxy,
  },
  preview: {
    host: '0.0.0.0',
    port: 43173,
    proxy,
  },
})
