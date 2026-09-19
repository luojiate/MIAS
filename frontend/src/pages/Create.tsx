import { useState, type ChangeEvent } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { createAnalysisRequest, uploadImageRequest } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/context/AuthContext'
import { getErrorMessage } from '@/lib/errors'
import { resolveImageUrl } from '@/lib/utils'
import type { UploadResult } from '@/types'

const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/gif']

type CreateForm = {
  number: string
  description: string
}

export function CreatePage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [result, setResult] = useState<UploadResult | null>(null)
  const [view, setView] = useState<'original' | 'overlay'>('overlay')
  const [fileError, setFileError] = useState<string | null>(null)
  const [serverError, setServerError] = useState<string | null>(null)
  const [status, setStatus] = useState<'idle' | 'analyzing' | 'saving'>('idle')
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CreateForm>()

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.files?.[0] ?? null
    setFileError(null)
    setServerError(null)
    setResult(null)
    setView('overlay')
    if (!next) {
      setFile(null)
      setPreview(null)
      return
    }
    if (!ACCEPTED_TYPES.includes(next.type)) {
      setFile(null)
      setPreview(null)
      setFileError('請選擇 JPG、PNG 或 GIF 圖片。')
      return
    }
    setFile(next)
    const reader = new FileReader()
    reader.onload = () => setPreview(typeof reader.result === 'string' ? reader.result : null)
    reader.readAsDataURL(next)
  }

  async function runAnalysis() {
    if (!file) {
      setFileError('請先選擇要分析的影像。')
      return
    }
    setServerError(null)
    setFileError(null)
    setStatus('analyzing')
    try {
      const uploaded = await uploadImageRequest(file)
      setResult(uploaded)
      setView(uploaded.overlay ? 'overlay' : 'original')
    } catch (error) {
      setServerError(getErrorMessage(error, '預測失敗，請再試一次。'))
    } finally {
      setStatus('idle')
    }
  }

  async function onSubmit(values: CreateForm) {
    if (!user) return
    if (!result?.image) {
      setFileError('請先執行「預測面積」再儲存。')
      return
    }
    setServerError(null)
    setStatus('saving')
    try {
      await createAnalysisRequest({
        number: values.number,
        description: values.description,
        userid: user.ID,
        image: result.image,
      })
      navigate('/personal')
    } catch (error) {
      setServerError(getErrorMessage(error, '儲存失敗，請再試一次。'))
    } finally {
      setStatus('idle')
    }
  }

  const busy = status !== 'idle'
  const displaySrc =
    view === 'overlay' && result?.overlay
      ? resolveImageUrl(result.overlay)
      : result?.image
        ? resolveImageUrl(result.image)
        : preview

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-10">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-white">新增分析</h1>
        <p className="mt-1 text-zinc-400">上傳影像後可先查看預測脂肪面積，再儲存到個人紀錄。</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="border-zinc-700 bg-zinc-900 text-zinc-100">
          <CardHeader>
            <CardTitle className="text-white">影像與預測區域</CardTitle>
            <CardDescription className="text-zinc-400">
              琥珀色 = 外層脂肪（outer），青色 = 內層脂肪（inner）
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="image" className="text-zinc-200">
                選擇影像
              </Label>
              <Input
                id="image"
                type="file"
                accept="image/jpeg,image/png,image/gif,.jpg,.jpeg,.png,.gif"
                onChange={onFileChange}
                disabled={busy}
                className="border-zinc-600 bg-zinc-950 text-zinc-100 file:text-zinc-200"
              />
              {fileError && <p className="text-sm text-red-400">{fileError}</p>}
            </div>

            <div className="overflow-hidden rounded-xl border border-zinc-700 bg-zinc-950">
              {displaySrc ? (
                <img
                  src={displaySrc}
                  alt="分析預覽"
                  className="max-h-[420px] w-full object-contain"
                />
              ) : (
                <div className="flex h-64 items-center justify-center text-sm text-zinc-500">
                  尚未選擇影像
                </div>
              )}
            </div>

            {result && (
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant={view === 'original' ? 'default' : 'secondary'}
                  onClick={() => setView('original')}
                  disabled={busy}
                >
                  原圖
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={view === 'overlay' ? 'default' : 'secondary'}
                  onClick={() => setView('overlay')}
                  disabled={busy || !result.overlay}
                >
                  預測面積
                </Button>
              </div>
            )}

            <div className="flex flex-wrap gap-3 text-xs text-zinc-300">
              <span className="inline-flex items-center gap-2 rounded-full border border-amber-500/40 bg-amber-500/10 px-3 py-1">
                <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
                Outer fat
              </span>
              <span className="inline-flex items-center gap-2 rounded-full border border-cyan-400/40 bg-cyan-400/10 px-3 py-1">
                <span className="h-2.5 w-2.5 rounded-full bg-cyan-300" />
                Inner fat
              </span>
            </div>

            <Button type="button" className="w-full" onClick={() => void runAnalysis()} disabled={busy || !file}>
              {status === 'analyzing' ? '預測中…' : '預測面積'}
            </Button>
          </CardContent>
        </Card>

        <Card className="border-zinc-700 bg-zinc-900 text-zinc-100">
          <CardHeader>
            <CardTitle className="text-white">數值與儲存</CardTitle>
            <CardDescription className="text-zinc-400">預測完成後填寫編號與說明並儲存。</CardDescription>
          </CardHeader>
          <CardContent>
            {serverError && (
              <p className="mb-4 rounded-md border border-red-400/40 bg-red-950/40 px-3 py-2 text-sm text-red-200" role="alert">
                {serverError}
              </p>
            )}

            <div className="mb-5 grid grid-cols-2 gap-3">
              {[
                { label: '外層脂肪 (cm²)', value: result?.outerFat },
                { label: '內層脂肪 (cm²)', value: result?.innerFat },
                { label: '長度 (cm)', value: result?.length },
                { label: '寬度 (cm)', value: result?.width },
              ].map((m) => (
                <div key={m.label} className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-3">
                  <p className="text-xs text-zinc-500">{m.label}</p>
                  <p className="mt-1 text-xl font-semibold text-white">
                    {m.value === undefined || m.value === null ? '—' : m.value}
                  </p>
                </div>
              ))}
            </div>

            <form className="space-y-5" onSubmit={handleSubmit(onSubmit)} noValidate>
              <div className="space-y-2">
                <Label htmlFor="number" className="text-zinc-200">
                  分析編號
                </Label>
                <Input
                  id="number"
                  placeholder="例如 A-1042"
                  {...register('number', { required: '請填寫分析編號' })}
                  disabled={busy}
                  className="border-zinc-600 bg-zinc-950 text-zinc-100"
                />
                {errors.number && <p className="text-sm text-red-400">{errors.number.message}</p>}
              </div>
              <div className="space-y-2">
                <Label htmlFor="description" className="text-zinc-200">
                  說明
                </Label>
                <textarea
                  id="description"
                  rows={4}
                  className="flex w-full rounded-md border border-zinc-600 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 shadow-sm placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
                  placeholder="這次掃描的備註"
                  {...register('description', { required: '請填寫說明' })}
                  disabled={busy}
                />
                {errors.description && <p className="text-sm text-red-400">{errors.description.message}</p>}
              </div>
              <Button type="submit" className="w-full" disabled={busy || !result}>
                {status === 'saving' ? '儲存中…' : '儲存分析'}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
