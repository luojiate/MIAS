import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Navbar } from '@/components/Navbar'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { AuthProvider } from '@/context/AuthContext'
import { CreatePage } from '@/pages/Create'
import { HomePage } from '@/pages/Home'
import { LoginPage } from '@/pages/Login'
import { PersonalPage } from '@/pages/Personal'
import { RegisterPage } from '@/pages/Register'

function AppLayout() {
  return (
    <div className="min-h-screen bg-zinc-800">
      <Navbar />
      <main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/create" element={<CreatePage />} />
            <Route path="/personal" element={<PersonalPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppLayout />
      </BrowserRouter>
    </AuthProvider>
  )
}
