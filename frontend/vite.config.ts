import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type ProxyOptions } from 'vite'

const backend = process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'

const alwaysProxy = [
  '/upload-image',
  '/upload-images',
  '/create-batch',
  '/delete',
  '/uploads',
  '/health',
  '/logout',
]

// These API paths also exist as React Router pages; GET HTML must stay in the SPA.
const spaColliding = ['/login', '/register', '/create', '/personal']

function htmlGetBypass(req: { method?: string; headers?: { accept?: string }; url?: string }) {
  const accept = req.headers?.accept ?? ''
  if (req.method === 'GET' && accept.includes('text/html')) {
    return req.url
  }
  return null
}

const proxy: Record<string, ProxyOptions> = {
  ...Object.fromEntries(
    alwaysProxy.map((p) => [p, { target: backend, changeOrigin: true }]),
  ),
  ...Object.fromEntries(
    spaColliding.map((p) => [
      p,
      { target: backend, changeOrigin: true, bypass: htmlGetBypass },
    ]),
  ),
}

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
