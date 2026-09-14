import { isAxiosError } from 'axios'

export function getErrorMessage(error: unknown, fallback = 'Something went wrong'): string {
  if (isAxiosError(error)) {
    const data = error.response?.data as unknown
    if (typeof data === 'string' && data.trim()) return data
    if (data && typeof data === 'object') {
      const rec = data as Record<string, unknown>
      const detail = rec.detail
      if (typeof detail === 'string' && detail.trim()) return detail
      if (Array.isArray(detail) && detail[0] && typeof detail[0] === 'object') {
        const first = detail[0] as { msg?: string }
        if (typeof first.msg === 'string' && first.msg.trim()) return first.msg
      }
      if (typeof rec.message === 'string' && rec.message.trim()) return rec.message
      if (typeof rec.error === 'string' && rec.error.trim()) return rec.error
    }
    if (error.response?.status === 401) return 'Please log in to continue.'
    if (error.message) return error.message
  }
  if (error instanceof Error && error.message) return error.message
  return fallback
}
