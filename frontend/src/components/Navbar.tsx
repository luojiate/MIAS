import { LogOut, ScanHeart } from 'lucide-react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/context/AuthContext'
import { cn } from '@/lib/utils'

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'rounded-md px-3 py-2 text-sm font-medium transition-colors',
    isActive ? 'bg-indigo-600 text-white' : 'text-zinc-200 hover:bg-zinc-800 hover:text-white',
  )

export function Navbar() {
  const { isAuthenticated, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/login')
  }

  return (
    <header className="sticky top-0 z-40 border-b border-indigo-700/40 bg-zinc-950/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
        <Link to="/" className="flex items-center gap-2 text-white">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600">
            <ScanHeart className="h-5 w-5" />
          </span>
          <span className="text-sm font-semibold tracking-wide sm:text-base">
            Medimage Analysis System
          </span>
        </Link>
        <nav className="flex flex-wrap items-center justify-end gap-1">
          <NavLink to="/" className={navLinkClass} end>
            Home
          </NavLink>
          <NavLink to="/create" className={navLinkClass}>
            Create
          </NavLink>
          {!isAuthenticated && (
            <>
              <NavLink to="/login" className={navLinkClass}>
                Login
              </NavLink>
              <NavLink to="/register" className={navLinkClass}>
                Register
              </NavLink>
            </>
          )}
          <NavLink to="/personal" className={navLinkClass}>
            My Post
          </NavLink>
          {isAuthenticated && (
            <Button variant="ghost" size="sm" onClick={() => void handleLogout()}>
              <LogOut />
              Log Out
            </Button>
          )}
        </nav>
      </div>
    </header>
  )
}
