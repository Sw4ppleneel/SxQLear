import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'

export function AppLayout() {
  const location = useLocation()

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-surface">
      <Sidebar />
      <main className="flex flex-1 flex-col overflow-hidden">
        {/* Keyed by path so a crash in one view doesn't stick around after navigating away */}
        <ErrorBoundary key={location.pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  )
}
