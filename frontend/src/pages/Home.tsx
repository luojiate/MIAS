import { ArrowRight, FolderOpen, PlusCircle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/context/AuthContext'

export function HomePage() {
  const { user, isAuthenticated } = useAuth()

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-10 px-4 py-12 sm:py-16">
      <section className="rounded-2xl border border-zinc-700 bg-zinc-900/80 p-8 shadow-xl sm:p-12">
        {isAuthenticated && user ? (
          <>
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-indigo-400">
              Signed in
            </p>
            <h1 className="mt-3 text-3xl font-bold text-white sm:text-5xl">Hi {user.name}</h1>
            <p className="mt-4 max-w-2xl text-base leading-relaxed text-zinc-300 sm:text-lg">
              Upload a scan, store measurements, and review every analysis tied to your account.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Button asChild size="lg">
                <Link to="/create">
                  <PlusCircle />
                  New Analysis
                  <ArrowRight />
                </Link>
              </Button>
              <Button asChild size="lg" variant="secondary">
                <Link to="/personal">
                  <FolderOpen />
                  My Analysis
                </Link>
              </Button>
            </div>
          </>
        ) : (
          <>
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-indigo-400">
              Medimage Analysis System
            </p>
            <h1 className="mt-3 text-3xl font-bold text-white sm:text-5xl">
              Measure, store, and review medical image analyses
            </h1>
            <p className="mt-4 max-w-2xl text-base leading-relaxed text-zinc-300 sm:text-lg">
              Sign in to upload images, run analysis, and keep a private history of outer fat,
              inner fat, length, and width measurements.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Button asChild size="lg">
                <Link to="/login">Log in</Link>
              </Button>
              <Button asChild size="lg" variant="secondary">
                <Link to="/register">Create an account</Link>
              </Button>
            </div>
          </>
        )}
      </section>
    </div>
  )
}
