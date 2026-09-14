import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Empty string uses the Vite proxy (same origin). */
export function getBackendUrl(): string {
  const raw = import.meta.env.VITE_BACKEND_URL
  if (raw === undefined || raw === null) return 'http://localhost:8000'
  return String(raw).replace(/\/$/, '')
}

export function resolveImageUrl(image: string | undefined | null): string {
  if (!image) return ''
  const backend = getBackendUrl()
  if (image.startsWith('http://') || image.startsWith('https://')) {
    if (!backend) {
      try {
        const url = new URL(image)
        if (url.pathname.startsWith('/uploads')) return url.pathname
      } catch {
        return image
      }
    }
    return image
  }
  const path = image.startsWith('/') ? image : `/uploads/${image}`
  return `${backend}${path}`
}
