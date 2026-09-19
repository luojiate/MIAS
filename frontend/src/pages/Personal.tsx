import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { deleteAnalysisRequest, listPersonalAnalyses } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { getErrorMessage } from '@/lib/errors'
import { resolveImageUrl } from '@/lib/utils'
import type { Analysis } from '@/types'

function metric(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

export function PersonalPage() {
  const [items, setItems] = useState<Analysis[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [showOverlay, setShowOverlay] = useState<Record<string, boolean>>({})

  async function load() {
    setError(null)
    try {
      const data = await listPersonalAnalyses()
      setItems(data)
      const defaults: Record<string, boolean> = {}
      for (const item of data) {
        defaults[item.id] = Boolean(item.overlay)
      }
      setShowOverlay(defaults)
    } catch (err) {
      setError(getErrorMessage(err, '無法載入分析紀錄。'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  async function handleDelete(id: string) {
    if (!window.confirm('確定刪除這筆分析？此操作無法復原。')) return
    setDeletingId(id)
    setError(null)
    try {
      await deleteAnalysisRequest(id)
      setItems((current) => current.filter((item) => item.id !== id))
    } catch (err) {
      setError(getErrorMessage(err, '刪除失敗。'))
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <div className="mb-8 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">我的分析</h1>
          <p className="mt-1 text-zinc-400">可切換原圖／預測面積疊圖檢視。</p>
        </div>
        <Button asChild>
          <Link to="/create">新增分析</Link>
        </Button>
      </div>

      {error && (
        <p className="mb-6 rounded-md border border-red-400/40 bg-red-950/40 px-4 py-3 text-sm text-red-200" role="alert">
          {error}
        </p>
      )}

      {loading && <p className="text-zinc-300">載入中…</p>}

      {!loading && items.length === 0 && (
        <Card className="border-dashed border-zinc-700 bg-zinc-900 text-zinc-100">
          <CardContent className="py-12 text-center">
            <p className="text-lg font-medium">尚無分析紀錄</p>
            <p className="mt-2 text-sm text-zinc-400">到「新增分析」上傳影像並預測面積。</p>
            <Button asChild className="mt-6">
              <Link to="/create">建立第一筆分析</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => {
          const useOverlay = showOverlay[item.id] && item.overlay
          const src = resolveImageUrl(useOverlay ? item.overlay : item.image)
          return (
            <article
              key={item.id}
              className="overflow-hidden rounded-xl border border-zinc-700 bg-zinc-900 shadow-lg"
            >
              <div className="aspect-[4/3] bg-zinc-800">
                {src ? (
                  <img src={src} alt={`Analysis ${item.number}`} className="h-full w-full object-contain bg-zinc-950" />
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-zinc-500">無影像</div>
                )}
              </div>
              <div className="space-y-3 p-4 text-zinc-100">
                <div>
                  <h2 className="text-lg font-semibold text-white">#{item.number}</h2>
                  <p className="mt-1 text-sm text-zinc-400">{item.description || '無說明'}</p>
                </div>
                {item.overlay && (
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant={!showOverlay[item.id] ? 'default' : 'secondary'}
                      onClick={() => setShowOverlay((s) => ({ ...s, [item.id]: false }))}
                    >
                      原圖
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant={showOverlay[item.id] ? 'default' : 'secondary'}
                      onClick={() => setShowOverlay((s) => ({ ...s, [item.id]: true }))}
                    >
                      預測面積
                    </Button>
                  </div>
                )}
                <dl className="grid grid-cols-2 gap-2 text-xs text-zinc-300">
                  <div>
                    <dt className="text-zinc-500">外層脂肪 (cm²)</dt>
                    <dd>{metric(item.outer_fat)}</dd>
                  </div>
                  <div>
                    <dt className="text-zinc-500">內層脂肪 (cm²)</dt>
                    <dd>{metric(item.inner_fat)}</dd>
                  </div>
                  <div>
                    <dt className="text-zinc-500">長度 (cm)</dt>
                    <dd>{metric(item.length)}</dd>
                  </div>
                  <div>
                    <dt className="text-zinc-500">寬度 (cm)</dt>
                    <dd>{metric(item.width)}</dd>
                  </div>
                </dl>
                <div className="flex flex-wrap gap-2 text-[11px] text-zinc-400">
                  <span className="inline-flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-amber-400" /> Outer
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-cyan-300" /> Inner
                  </span>
                </div>
                <Button
                  variant="destructive"
                  size="sm"
                  className="w-full"
                  disabled={deletingId === item.id}
                  onClick={() => void handleDelete(item.id)}
                >
                  {deletingId === item.id ? '刪除中…' : '刪除'}
                </Button>
              </div>
            </article>
          )
        })}
      </div>
    </div>
  )
}
