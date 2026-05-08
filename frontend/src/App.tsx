import React, { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, Outlet, useParams } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { AppLayout } from '@/components/layout/AppLayout'
import { ConnectionView } from '@/views/ConnectionView'
import { SchemaView } from '@/views/SchemaView'
import { InferenceView } from '@/views/InferenceView'
import { ValidationView } from '@/views/ValidationView'
import { MemoryView } from '@/views/MemoryView'
import { DatasetView } from '@/views/DatasetView'
import { useProjectStore } from '@/stores/projectStore'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 30_000,
      retry: 1,
    },
  },
})

/** Syncs the URL :projectId param into the project store on every navigation. */
function ProjectLayout() {
  const { projectId } = useParams<{ projectId: string }>()
  const { activeProjectId, setActiveProject } = useProjectStore()

  useEffect(() => {
    if (projectId && projectId !== activeProjectId) {
      setActiveProject(projectId)
    }
  }, [projectId, activeProjectId, setActiveProject])

  return <Outlet />
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<ConnectionView />} />
            <Route element={<ProjectLayout />}>
              <Route path="/projects/:projectId/schema" element={<SchemaView />} />
              <Route path="/projects/:projectId/inference" element={<InferenceView />} />
              <Route path="/projects/:projectId/validation" element={<ValidationView />} />
              <Route path="/projects/:projectId/memory" element={<MemoryView />} />
              <Route path="/projects/:projectId/datasets" element={<DatasetView />} />
            </Route>
            {/* Fallback */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: '#1a1a1a',
            color: '#e8e8e8',
            border: '1px solid #2a2a2a',
            fontSize: '13px',
          },
          success: { iconTheme: { primary: '#22c55e', secondary: '#111' } },
          error: { iconTheme: { primary: '#ef4444', secondary: '#111' } },
        }}
      />
    </QueryClientProvider>
  )
}
