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

  async function load() {
    setError(null)
    try {
      const data = await listPersonalAnalyses()
      setItems(data)
    } catch (err) {
      setError(getErrorMessage(err, 'Could not load your analyses.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  async function handleDelete(id: string) {
    if (!window.confirm('Delete this analysis? This cannot be undone.')) return
    setDeletingId(id)
    setError(null)
    try {
      await deleteAnalysisRequest(id)
      setItems((current) => current.filter((item) => item.id !== id))
    } catch (err) {
      setError(getErrorMessage(err, 'Could not delete this analysis.'))
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <div className="mb-8 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">My Analysis</h1>
          <p className="mt-1 text-zinc-400">Records saved to your account, including image metrics.</p>
        </div>
        <Button asChild>
          <Link to="/create">New analysis</Link>
        </Button>
      </div>

      {error && (
        <p className="mb-6 rounded-md border border-red-400/40 bg-red-950/40 px-4 py-3 text-sm text-red-200" role="alert">
          {error}
        </p>
      )}

      {loading && <p className="text-zinc-300">Loading your analyses…</p>}

      {!loading && items.length === 0 && (
        <Card className="border-dashed bg-zinc-900 text-zinc-100">
          <CardContent className="py-12 text-center">
            <p className="text-lg font-medium">You have not created any analyses yet.</p>
            <p className="mt-2 text-sm text-zinc-400">Upload an image from Create to see it here.</p>
            <Button asChild className="mt-6">
              <Link to="/create">Create your first analysis</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => (
          <article
            key={item.id}
            className="overflow-hidden rounded-xl border border-zinc-700 bg-zinc-900 shadow-lg"
          >
            <div className="aspect-[4/3] bg-zinc-800">
              {item.image ? (
                <img
                  src={resolveImageUrl(item.image)}
                  alt={`Analysis ${item.number}`}
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-zinc-500">
                  No image
                </div>
              )}
            </div>
            <div className="space-y-3 p-4 text-zinc-100">
              <div>
                <h2 className="text-lg font-semibold text-white">#{item.number}</h2>
                <p className="mt-1 text-sm text-zinc-400">{item.description || 'No description'}</p>
              </div>
              <dl className="grid grid-cols-2 gap-2 text-xs text-zinc-300">
                <div>
                  <dt className="text-zinc-500">Outer fat</dt>
                  <dd>{metric(item.outer_fat)}</dd>
                </div>
                <div>
                  <dt className="text-zinc-500">Inner fat</dt>
                  <dd>{metric(item.inner_fat)}</dd>
                </div>
                <div>
                  <dt className="text-zinc-500">Length</dt>
                  <dd>{metric(item.length)}</dd>
                </div>
                <div>
                  <dt className="text-zinc-500">Width</dt>
                  <dd>{metric(item.width)}</dd>
                </div>
              </dl>
              <Button
                variant="destructive"
                size="sm"
                className="w-full"
                disabled={deletingId === item.id}
                onClick={() => void handleDelete(item.id)}
              >
                {deletingId === item.id ? 'Deleting…' : 'Delete'}
              </Button>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
