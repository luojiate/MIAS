import axios, { isAxiosError } from 'axios'
import { getBackendUrl } from '@/lib/utils'
import type { Analysis, UploadResult, User } from '@/types'

export const api = axios.create({
  baseURL: getBackendUrl(),
  withCredentials: true,
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (isAxiosError(error) && error.response?.status === 401) {
      const url = String(error.config?.url ?? '')
      const isAuthAttempt = url.includes('/login') || url.includes('/register')
      if (!isAuthAttempt) {
        localStorage.removeItem('user')
        if (window.location.pathname !== '/login') {
          window.location.assign('/login')
        }
      }
    }
    return Promise.reject(error)
  },
)

function asUser(value: unknown): User {
  if (!value || typeof value !== 'object') {
    throw new Error('Login succeeded but no user was returned.')
  }
  const rec = value as Record<string, unknown>
  const id = rec.ID ?? rec.id ?? rec._id
  if (typeof rec.name !== 'string' || typeof rec.email !== 'string' || id == null) {
    throw new Error('Login succeeded but the user payload was incomplete.')
  }
  return {
    ...(rec as User),
    ID: String(id),
    name: rec.name,
    email: rec.email,
  }
}

export async function loginRequest(email: string, password: string): Promise<User> {
  const { data } = await api.post('/login', { email, password })
  return asUser(data?.user ?? data)
}

export async function registerRequest(payload: {
  name: string
  email: string
  password: string
}): Promise<void> {
  await api.post('/register', payload)
}

export async function logoutRequest(): Promise<void> {
  try {
    await api.post('/logout')
  } catch {
    // Still clear the local session even if the server is unreachable.
  }
}

export async function uploadImageRequest(file: File): Promise<UploadResult> {
  const form = new FormData()
  form.append('image', file)
  form.append('name', file.name)
  const { data } = await api.post('/upload-image', form)
  const image =
    (typeof data?.image === 'string' && data.image) ||
    (typeof data?.url === 'string' && data.url) ||
    (typeof data === 'string' ? data : '')
  if (!image) {
    throw new Error('Upload succeeded but no image URL was returned.')
  }
  return { ...data, image }
}

export async function createAnalysisRequest(payload: {
  number: string
  description: string
  userid: string
  image?: string
}): Promise<void> {
  await api.post('/create', payload)
}

export async function listPersonalAnalyses(): Promise<Analysis[]> {
  const { data } = await api.get('/personal')
  if (!Array.isArray(data)) return []
  return data.map((item: Record<string, unknown>) => ({
    id: String(item.id ?? item._id ?? ''),
    image: String(item.image ?? ''),
    number: (item.number as string | number) ?? '',
    description: String(item.description ?? ''),
    userid: String(item.userid ?? ''),
    outer_fat: (item.outer_fat as number | string | null) ?? null,
    inner_fat: (item.inner_fat as number | string | null) ?? null,
    length: (item.length as number | string | null) ?? null,
    width: (item.width as number | string | null) ?? null,
  }))
}

export async function deleteAnalysisRequest(id: string): Promise<void> {
  await api.delete(`/delete/${id}`)
}
