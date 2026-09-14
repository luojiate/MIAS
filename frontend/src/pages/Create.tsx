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
  const [fileError, setFileError] = useState<string | null>(null)
  const [serverError, setServerError] = useState<string | null>(null)
  const [status, setStatus] = useState<'idle' | 'uploading' | 'creating'>('idle')
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CreateForm>()

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.files?.[0] ?? null
    setFileError(null)
    setServerError(null)
    if (!next) {
      setFile(null)
      setPreview(null)
      return
    }
    if (!ACCEPTED_TYPES.includes(next.type)) {
      setFile(null)
      setPreview(null)
      setFileError('Please choose a JPG, PNG, or GIF image.')
      return
    }
    setFile(next)
    const reader = new FileReader()
    reader.onload = () => setPreview(typeof reader.result === 'string' ? reader.result : null)
    reader.readAsDataURL(next)
  }

  async function onSubmit(values: CreateForm) {
    if (!user) return
    if (!file) {
      setFileError('Please choose an image to upload.')
      return
    }
    setServerError(null)
    setFileError(null)
    try {
      setStatus('uploading')
      const uploaded = await uploadImageRequest(file)
      setStatus('creating')
      await createAnalysisRequest({
        number: values.number,
        description: values.description,
        userid: user.ID,
        image: uploaded.image,
      })
      navigate('/personal')
    } catch (error) {
      setServerError(getErrorMessage(error, 'Could not create the analysis. Try again.'))
    } finally {
      setStatus('idle')
    }
  }

  const busy = status !== 'idle'
  const submitLabel =
    status === 'uploading' ? 'Uploading image…' : status === 'creating' ? 'Saving analysis…' : 'Create analysis'

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-10">
      <Card>
        <CardHeader>
          <CardTitle>New analysis</CardTitle>
          <CardDescription>
            Upload a JPG, PNG, or GIF. Image metrics are stored with your session, then saved when you
            create the record.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-5" onSubmit={handleSubmit(onSubmit)} noValidate>
            {serverError && (
              <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                {serverError}
              </p>
            )}
            <div className="space-y-2">
              <Label htmlFor="image">Image</Label>
              <Input
                id="image"
                type="file"
                accept="image/jpeg,image/png,image/gif,.jpg,.jpeg,.png,.gif"
                onChange={onFileChange}
                disabled={busy}
              />
              {fileError && <p className="text-sm text-red-600">{fileError}</p>}
              {preview && (
                <div className="overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50">
                  <img src={preview} alt="Selected scan preview" className="max-h-72 w-full object-contain" />
                </div>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="number">Analysis number</Label>
              <Input
                id="number"
                placeholder="e.g. A-1042"
                {...register('number', { required: 'Analysis number is required' })}
                disabled={busy}
              />
              {errors.number && <p className="text-sm text-red-600">{errors.number.message}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <textarea
                id="description"
                rows={4}
                className="flex w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 shadow-sm placeholder:text-zinc-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
                placeholder="Notes about this scan"
                {...register('description', { required: 'Description is required' })}
                disabled={busy}
              />
              {errors.description && (
                <p className="text-sm text-red-600">{errors.description.message}</p>
              )}
            </div>
            <Button type="submit" className="w-full" disabled={busy}>
              {submitLabel}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
