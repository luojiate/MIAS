export type User = {
  ID: string
  name: string
  email: string
  [key: string]: unknown
}

export type Analysis = {
  id: string
  image: string
  overlay?: string
  inner_mask?: string
  outer_mask?: string
  number: string | number
  description: string
  userid: string
  outer_fat: number | string | null
  inner_fat: number | string | null
  length: number | string | null
  width: number | string | null
}

export type UploadResult = {
  image: string
  overlay?: string | null
  innerMask?: string | null
  outerMask?: string | null
  outerFat?: number
  innerFat?: number
  length?: number
  width?: number
  url?: string
}

export type BatchQueueStatus = 'pending' | 'running' | 'success' | 'failed'

export type BatchAnalysisItem = UploadResult & {
  index: number
  filename: string
  success: boolean
  error?: string | null
}

export type BatchUploadResponse = {
  message: string
  results: BatchAnalysisItem[]
  succeeded: number
  failed: number
}

export type CreateBatchItem = {
  number: string
  description: string
  image: string
  overlay?: string | null
  inner_mask?: string | null
  outer_mask?: string | null
  outer_fat?: number
  inner_fat?: number
  length?: number
  width?: number
}
