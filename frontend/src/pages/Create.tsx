import { useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { createBatchRequest, uploadImagesRequest } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/context/AuthContext'
import { getErrorMessage } from '@/lib/errors'
import { cn, resolveImageUrl } from '@/lib/utils'
import type { BatchQueueStatus, UploadResult } from '@/types'

const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/gif']
const ACCEPTED_EXTS = ['.jpg', '.jpeg', '.png', '.gif']
const MAX_BATCH_FILES = 8
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024

type CreateForm = {
  number: string
  description: string
}

type QueueItem = {
  id: string
  file: File
  filename: string
  status: BatchQueueStatus
  error: string | null
  preview: string
  result: UploadResult | null
}

function hasAcceptedExtension(name: string) {
  const lower = name.toLowerCase()
  return ACCEPTED_EXTS.some((ext) => lower.endsWith(ext))
}

function validateFile(file: File): string | null {
  if (!ACCEPTED_TYPES.includes(file.type) && !hasAcceptedExtension(file.name)) {
    return '請選擇 JPG、PNG 或 GIF 圖片。'
  }
  if (file.size === 0) return '上傳的檔案是空的。'
  if (file.size > MAX_UPLOAD_BYTES) return '檔案超過 10 MB 上限。'
  return null
}

function statusLabel(status: BatchQueueStatus) {
  switch (status) {
    case 'pending':
      return '等待中'
    case 'running':
      return '分析中'
    case 'success':
      return '完成'
    case 'failed':
      return '失敗'
  }
}

function padIndex(index: number) {
  return String(index + 1).padStart(2, '0')
}

function revokePreviews(rows: QueueItem[]) {
  for (const item of rows) URL.revokeObjectURL(item.preview)
}

export function CreatePage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const itemsRef = useRef<QueueItem[]>([])
  const [items, setItems] = useState<QueueItem[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [view, setView] = useState<'original' | 'overlay'>('overlay')
  const [fileError, setFileError] = useState<string | null>(null)
  const [serverError, setServerError] = useState<string | null>(null)
  const [status, setStatus] = useState<'idle' | 'analyzing' | 'saving'>('idle')
  const [dragging, setDragging] = useState(false)
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CreateForm>()

  useEffect(() => {
    itemsRef.current = items
  }, [items])

  useEffect(() => {
    return () => revokePreviews(itemsRef.current)
  }, [])

  const selected = items.find((item) => item.id === selectedId) ?? items[0] ?? null
  const successItems = useMemo(
    () => items.filter((item) => item.status === 'success' && item.result?.image),
    [items],
  )
  const uploadableCount = items.filter((item) => validateFile(item.file) === null).length
  const busy = status !== 'idle'

  function addFiles(nextFiles: File[], replace: boolean) {
    setServerError(null)
    setView('overlay')

    const incoming = Array.from(nextFiles)
    setItems((current) => {
      const base = replace ? [] : current
      if (replace) revokePreviews(current)
      const room = MAX_BATCH_FILES - base.length
      if (incoming.length === 0) {
        setFileError(null)
        if (replace) setSelectedId(null)
        return base
      }
      if (room <= 0) {
        setFileError(`一次最多上傳 ${MAX_BATCH_FILES} 張影像。`)
        return base
      }
      const accepted = incoming.slice(0, room)
      setFileError(
        incoming.length > room ? `一次最多上傳 ${MAX_BATCH_FILES} 張影像，已略過多餘檔案。` : null,
      )
      const created: QueueItem[] = accepted.map((file) => {
        const error = validateFile(file)
        return {
          id: crypto.randomUUID(),
          file,
          filename: file.name,
          status: error ? 'failed' : 'pending',
          error,
          preview: URL.createObjectURL(file),
          result: null,
        }
      })
      const next = [...base, ...created]
      setSelectedId((prev) => {
        if (!replace && prev && next.some((item) => item.id === prev)) return prev
        return created[0]?.id ?? next[0]?.id ?? null
      })
      return next
    })
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const list = event.target.files ? Array.from(event.target.files) : []
    addFiles(list, true)
    event.target.value = ''
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragging(false)
    if (busy) return
    const list = Array.from(event.dataTransfer.files || [])
    if (!list.length) return
    addFiles(list, false)
  }

  function removeItem(id: string) {
    if (busy) return
    setItems((current) => {
      const target = current.find((item) => item.id === id)
      if (target) URL.revokeObjectURL(target.preview)
      const next = current.filter((item) => item.id !== id)
      setSelectedId((prev) => (prev === id ? (next[0]?.id ?? null) : prev))
      return next
    })
    setFileError(null)
  }

  async function runAnalysis() {
    const toSend = items.filter((item) => validateFile(item.file) === null)
    if (!items.length) {
      setFileError('請先選擇要分析的影像。')
      return
    }
    if (!toSend.length) {
      setFileError('沒有可分析的影像，請改選 JPG、PNG 或 GIF。')
      return
    }
    setServerError(null)
    setFileError(null)
    setStatus('analyzing')
    setItems((current) =>
      current.map((item) =>
        toSend.some((row) => row.id === item.id)
          ? { ...item, status: 'running', error: null }
          : item,
      ),
    )
    try {
      const uploaded = await uploadImagesRequest(toSend.map((item) => item.file))
      let firstSuccessId: string | null = null
      let firstHasOverlay = false
      setItems((current) =>
        current.map((item) => {
          const index = toSend.findIndex((row) => row.id === item.id)
          if (index < 0) return item
          const row = uploaded.results[index]
          if (!row?.success || !row.image) {
            return { ...item, status: 'failed', error: row?.error || '分析失敗，請再試一次。', result: null }
          }
          if (!firstSuccessId) {
            firstSuccessId = item.id
            firstHasOverlay = Boolean(row.overlay)
          }
          const result: UploadResult = {
            image: row.image,
            overlay: row.overlay,
            innerMask: row.innerMask,
            outerMask: row.outerMask,
            outerFat: row.outerFat,
            innerFat: row.innerFat,
            length: row.length,
            width: row.width,
            url: row.url,
          }
          return { ...item, status: 'success', error: null, result }
        }),
      )
      if (firstSuccessId) {
        setSelectedId(firstSuccessId)
        setView(firstHasOverlay ? 'overlay' : 'original')
      }
    } catch (error) {
      setServerError(getErrorMessage(error, '預測失敗，請再試一次。'))
      setItems((current) =>
        current.map((item) => (item.status === 'running' ? { ...item, status: 'pending', error: null } : item)),
      )
    } finally {
      setStatus('idle')
    }
  }

  async function onSubmit(values: CreateForm) {
    if (!user) return
    if (!successItems.length) {
      setFileError('請先執行「預測面積」再儲存。')
      return
    }
    setServerError(null)
    setStatus('saving')
    try {
      await createBatchRequest({
        userid: user.ID,
        items: successItems.map((item, index) => ({
          number: successItems.length === 1 ? values.number : `${values.number}-${padIndex(index)}`,
          description: values.description,
          image: item.result!.image,
          overlay: item.result?.overlay ?? '',
          inner_mask: item.result?.innerMask ?? '',
          outer_mask: item.result?.outerMask ?? '',
          outer_fat: item.result?.outerFat ?? 0,
          inner_fat: item.result?.innerFat ?? 0,
          length: item.result?.length ?? 0,
          width: item.result?.width ?? 0,
        })),
      })
      navigate('/personal')
    } catch (error) {
      setServerError(getErrorMessage(error, '儲存失敗，請再試一次。'))
    } finally {
      setStatus('idle')
    }
  }

  const displaySrc =
    view === 'overlay' && selected?.result?.overlay
      ? resolveImageUrl(selected.result.overlay)
      : selected?.result?.image
        ? resolveImageUrl(selected.result.image)
        : selected?.preview ?? null

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-10">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-white">新增分析</h1>
        <p className="mt-1 text-zinc-400">
          可一次選擇多張醫學影像，依序執行脂肪分割預測後再儲存到個人紀錄。
        </p>
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
                選擇影像（可多選）
              </Label>
              <div
                onDragEnter={(event) => {
                  event.preventDefault()
                  if (!busy) setDragging(true)
                }}
                onDragOver={(event) => {
                  event.preventDefault()
                  if (!busy) setDragging(true)
                }}
                onDragLeave={(event) => {
                  event.preventDefault()
                  setDragging(false)
                }}
                onDrop={onDrop}
                className={cn(
                  'rounded-xl border border-dashed px-3 py-4 transition-colors',
                  dragging ? 'border-indigo-400 bg-indigo-500/10' : 'border-zinc-600 bg-zinc-950',
                )}
              >
                <Input
                  id="image"
                  type="file"
                  multiple
                  accept="image/jpeg,image/png,image/gif,.jpg,.jpeg,.png,.gif"
                  onChange={onFileChange}
                  disabled={busy}
                  className="border-zinc-600 bg-zinc-950 text-zinc-100 file:text-zinc-200"
                />
                <p className="mt-2 text-xs text-zinc-500">
                  可拖放或一次選擇最多 {MAX_BATCH_FILES} 張 JPG、PNG 或 GIF（每張上限 10 MB）。伺服器會依序分析以免記憶體不足。
                </p>
              </div>
              {fileError && <p className="text-sm text-red-400">{fileError}</p>}
            </div>

            {items.length > 0 && (
              <ul className="max-h-56 space-y-2 overflow-auto rounded-xl border border-zinc-700 bg-zinc-950 p-2">
                {items.map((item) => (
                  <li key={item.id}>
                    <div
                      className={cn(
                        'flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm',
                        selected?.id === item.id ? 'bg-zinc-800' : 'hover:bg-zinc-900',
                      )}
                    >
                      <button
                        type="button"
                        className="min-w-0 flex-1 text-left"
                        onClick={() => {
                          setSelectedId(item.id)
                          setView(item.result?.overlay ? 'overlay' : 'original')
                        }}
                        disabled={busy}
                      >
                        <p className="truncate font-medium text-zinc-100">{item.filename}</p>
                        <p
                          className={cn(
                            'mt-0.5 text-xs',
                            item.status === 'success' && 'text-emerald-400',
                            item.status === 'failed' && 'text-red-400',
                            item.status === 'running' && 'text-indigo-300',
                            item.status === 'pending' && 'text-zinc-500',
                          )}
                        >
                          {statusLabel(item.status)}
                          {item.error ? `：${item.error}` : ''}
                        </p>
                      </button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => removeItem(item.id)}
                        disabled={busy}
                        aria-label={`移除 ${item.filename}`}
                      >
                        移除
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}

            <div className="overflow-hidden rounded-xl border border-zinc-700 bg-zinc-950">
              {displaySrc ? (
                <img
                  src={displaySrc}
                  alt={selected ? `${selected.filename} 預覽` : '分析預覽'}
                  className="max-h-[420px] w-full object-contain"
                />
              ) : (
                <div className="flex h-64 items-center justify-center text-sm text-zinc-500">
                  尚未選擇影像
                </div>
              )}
            </div>

            {selected?.result && (
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
                  disabled={busy || !selected.result.overlay}
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

            <Button
              type="button"
              className="w-full"
              onClick={() => void runAnalysis()}
              disabled={busy || !items.length}
            >
              {status === 'analyzing'
                ? items.length > 1
                  ? `批次預測中（${items.length} 張，請稍候）…`
                  : '預測中…'
                : items.length > 1
                  ? `批次預測（${uploadableCount || items.length} 張）`
                  : '預測面積'}
            </Button>
          </CardContent>
        </Card>

        <Card className="border-zinc-700 bg-zinc-900 text-zinc-100">
          <CardHeader>
            <CardTitle className="text-white">數值與儲存</CardTitle>
            <CardDescription className="text-zinc-400">
              預測完成後填寫編號與說明。多張影像會以編號-01、編號-02 依序存成多筆紀錄。
            </CardDescription>
          </CardHeader>
          <CardContent>
            {serverError && (
              <p className="mb-4 rounded-md border border-red-400/40 bg-red-950/40 px-3 py-2 text-sm text-red-200" role="alert">
                {serverError}
              </p>
            )}

            <p className="mb-3 text-xs text-zinc-500">
              {selected ? `目前檢視：${selected.filename}` : '選擇佇列中的檔案以查看量測值。'}
            </p>

            <div className="mb-5 grid grid-cols-2 gap-3">
              {[
                { label: '外層脂肪 (cm²)', value: selected?.result?.outerFat },
                { label: '內層脂肪 (cm²)', value: selected?.result?.innerFat },
                { label: '長度 (cm)', value: selected?.result?.length },
                { label: '寬度 (cm)', value: selected?.result?.width },
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
              <Button type="submit" className="w-full" disabled={busy || successItems.length === 0}>
                {status === 'saving'
                  ? '儲存中…'
                  : successItems.length > 1
                    ? `儲存全部（${successItems.length} 筆）`
                    : '儲存分析'}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
