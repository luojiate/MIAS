export type User = {
  ID: string
  name: string
  email: string
  [key: string]: unknown
}

export type Analysis = {
  id: string
  image: string
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
  outerFat?: number
  innerFat?: number
  length?: number
  width?: number
  url?: string
}
