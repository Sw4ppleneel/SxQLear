import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Plus, Database, ArrowRight, Pencil, Trash2 } from 'lucide-react'
import {
  createProject,
  listProjects,
  testConnection,
  getProjectConnection,
  updateProject,
  deleteProject,
} from '@/lib/api'
import { Button } from '@/components/common/Button'
import { useProjectStore } from '@/stores/projectStore'
import type { DatabaseDialect, Project } from '@/types'
import { cn, formatDate } from '@/lib/utils'

const DIALECTS: Array<{ value: DatabaseDialect; label: string }> = [
  { value: 'postgresql', label: 'PostgreSQL' },
  { value: 'mysql', label: 'MySQL' },
  { value: 'sqlite', label: 'SQLite' },
  { value: 'mssql', label: 'SQL Server' },
]

interface FormValues {
  name: string
  description: string
  dialect: DatabaseDialect
  host: string
  port: string
  database: string
  username: string
  password: string
}

const INITIAL_FORM: FormValues = {
  name: '',
  description: '',
  dialect: 'postgresql',
  host: 'localhost',
  port: '5432',
  database: '',
  username: '',
  password: '',
}

type PanelMode = 'new' | 'edit'

export function ConnectionView() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { setActiveProject, addProject, activeProjectId } = useProjectStore()
  const [panelMode, setPanelMode] = useState<PanelMode | null>(null)
  const [editProjectId, setEditProjectId] = useState<string | null>(null)
  const [form, setForm] = useState<FormValues>(INITIAL_FORM)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: listProjects,
  })

  // Load existing connection config when opening edit panel
  const { data: configData, isFetching: loadingConfig } = useQuery({
    queryKey: ['connection', editProjectId],
    queryFn: () => getProjectConnection(editProjectId!),
    enabled: !!editProjectId && panelMode === 'edit',
    retry: false,
    staleTime: 0,
  })

  // Pre-fill the form when config data arrives
  useEffect(() => {
    if (configData && editProjectId && panelMode === 'edit') {
      const existing = projects.find((p) => p.id === editProjectId)
      setForm({
        name: existing?.name ?? '',
        description: existing?.description ?? '',
        dialect: (configData.dialect as DatabaseDialect) ?? 'sqlite',
        host: String(configData.host ?? ''),
        port: String(configData.port ?? ''),
        database: String(configData.database ?? ''),
        username: String(configData.username ?? ''),
        password: '',
      })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [configData, editProjectId])

  const testMutation = useMutation({
    mutationFn: () =>
      testConnection({
        name: form.name || 'test',
        dialect: form.dialect,
        host: form.host || undefined,
        port: form.port ? parseInt(form.port) : undefined,
        database: form.database,
        username: form.username || undefined,
        password: form.password || undefined,
      }),
    onSuccess: (result) => {
      if (result.success) {
        setTestResult({ success: true, message: `Connected in ${result.latency_ms?.toFixed(0)}ms` })
      } else {
        setTestResult({ success: false, message: result.error ?? 'Connection failed' })
      }
    },
    onError: () => setTestResult({ success: false, message: 'Request failed' }),
  })

  const createMutation = useMutation({
    mutationFn: () =>
      createProject({
        name: form.name,
        description: form.description || undefined,
        dialect: form.dialect,
        host: form.host || undefined,
        port: form.port ? parseInt(form.port) : undefined,
        database: form.database,
        username: form.username || undefined,
        password: form.password || undefined,
      }),
    onSuccess: (project) => {
      addProject(project)
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      toast.success(`Project "${project.name}" created`)
      closePanel()
      setActiveProject(project.id)
      navigate(`/projects/${project.id}/schema`)
    },
    onError: () => toast.error('Failed to create project'),
  })

  const updateMutation = useMutation({
    mutationFn: () =>
      updateProject(editProjectId!, {
        name: form.name || undefined,
        description: form.description || undefined,
        dialect: form.dialect,
        host: form.host || undefined,
        port: form.port ? parseInt(form.port) : undefined,
        database: form.database || undefined,
        username: form.username || undefined,
        password: form.password || undefined,
      }),
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      queryClient.invalidateQueries({ queryKey: ['connection', editProjectId] })
      toast.success(`Project "${project.name}" updated`)
      closePanel()
    },
    onError: () => toast.error('Failed to update project'),
  })

  const deleteMutation = useMutation({
    mutationFn: (projectId: string) => deleteProject(projectId),
    onSuccess: (_, projectId) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      toast.success('Project deleted')
      if (activeProjectId === projectId) {
        setActiveProject(null)
      }
    },
    onError: () => toast.error('Failed to delete project'),
  })

  function openNew() {
    setPanelMode('new')
    setEditProjectId(null)
    setForm(INITIAL_FORM)
    setTestResult(null)
  }

  function openEdit(projectId: string) {
    setPanelMode('edit')
    setEditProjectId(projectId)
    setForm(INITIAL_FORM)
    setTestResult(null)
  }

  function closePanel() {
    setPanelMode(null)
    setEditProjectId(null)
    setForm(INITIAL_FORM)
    setTestResult(null)
  }

  function setField(field: keyof FormValues, value: string) {
    setForm((f) => ({ ...f, [field]: value }))
    setTestResult(null)
  }

  function handleDialectChange(dialect: DatabaseDialect) {
    const defaultPorts: Partial<Record<DatabaseDialect, string>> = {
      postgresql: '5432',
      mysql: '3306',
      mssql: '1433',
    }
    setForm((f) => ({ ...f, dialect, port: defaultPorts[dialect] ?? '' }))
    setTestResult(null)
  }

  const isSQLite = form.dialect === 'sqlite'
  const isEditing = panelMode === 'edit'

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-surface-border px-6 py-4">
        <div>
          <h1 className="text-base font-semibold text-text-primary">Projects</h1>
          <p className="text-sm text-text-secondary">Connect to a database to start analyzing</p>
        </div>
        <Button variant="primary" onClick={openNew}>
          <Plus className="h-3.5 w-3.5" />
          New Project
        </Button>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-y-auto p-6">
          {projects.length === 0 && !panelMode ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
              <Database className="h-10 w-10 text-text-muted" />
              <p className="text-text-secondary text-sm">No projects yet</p>
              <p className="text-text-muted text-xs max-w-xs">
                Create a project by connecting to a database. SxQLear will crawl
                the schema and start building your analytical memory.
              </p>
              <Button variant="primary" size="sm" onClick={openNew}>
                Connect to a database
              </Button>
            </div>
          ) : (
            <div className="grid gap-3">
              {projects.map((project) => (
                <ProjectCard
                  key={project.id}
                  project={project}
                  isEditing={editProjectId === project.id}
                  onOpen={() => {
                    setActiveProject(project.id)
                    navigate(`/projects/${project.id}/schema`)
                  }}
                  onEdit={() => openEdit(project.id)}
                  onDelete={() => {
                    if (window.confirm(`Delete project "${project.name}"? This cannot be undone.`)) {
                      deleteMutation.mutate(project.id)
                    }
                  }}
                />
              ))}
            </div>
          )}
        </div>

        {panelMode && (
          <div className="w-96 flex-shrink-0 overflow-y-auto border-l border-surface-border bg-surface-elevated p-6">
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-primary">
                {isEditing ? 'Edit Connection' : 'New Project'}
              </h2>
              <button
                onClick={closePanel}
                className="text-text-muted hover:text-text-secondary text-xs"
              >
                Cancel
              </button>
            </div>

            {isEditing && loadingConfig ? (
              <p className="text-xs text-text-secondary">Loading connection details…</p>
            ) : (
              <div className="space-y-4">
                <Field label="Project name">
                  <input
                    className={inputClass}
                    placeholder="My Analytics DB"
                    value={form.name}
                    onChange={(e) => setField('name', e.target.value)}
                  />
                </Field>

                {!isEditing && (
                  <Field label="Description">
                    <input
                      className={inputClass}
                      placeholder="Optional description"
                      value={form.description}
                      onChange={(e) => setField('description', e.target.value)}
                    />
                  </Field>
                )}

                <Field label="Dialect">
                  <select
                    className={inputClass}
                    value={form.dialect}
                    onChange={(e) => handleDialectChange(e.target.value as DatabaseDialect)}
                  >
                    {DIALECTS.map((d) => (
                      <option key={d.value} value={d.value}>{d.label}</option>
                    ))}
                  </select>
                </Field>

                {isSQLite ? (
                  <Field label="File path">
                    <input
                      className={inputClass}
                      placeholder="/path/to/database.db"
                      value={form.database}
                      onChange={(e) => setField('database', e.target.value)}
                    />
                  </Field>
                ) : (
                  <>
                    <div className="grid grid-cols-3 gap-2">
                      <div className="col-span-2">
                        <Field label="Host">
                          <input
                            className={inputClass}
                            value={form.host}
                            onChange={(e) => setField('host', e.target.value)}
                          />
                        </Field>
                      </div>
                      <Field label="Port">
                        <input
                          className={inputClass}
                          value={form.port}
                          onChange={(e) => setField('port', e.target.value)}
                        />
                      </Field>
                    </div>
                    <Field label="Database">
                      <input
                        className={inputClass}
                        value={form.database}
                        onChange={(e) => setField('database', e.target.value)}
                      />
                    </Field>
                    <Field label="Username">
                      <input
                        className={inputClass}
                        value={form.username}
                        onChange={(e) => setField('username', e.target.value)}
                      />
                    </Field>
                    <Field label={isEditing ? 'Password (leave blank to keep existing)' : 'Password'}>
                      <input
                        type="password"
                        className={inputClass}
                        placeholder={isEditing ? '••••••••' : ''}
                        value={form.password}
                        onChange={(e) => setField('password', e.target.value)}
                      />
                    </Field>
                  </>
                )}

                {testResult && (
                  <p className={cn('text-xs', testResult.success ? 'text-status-confirmed' : 'text-status-rejected')}>
                    {testResult.success ? '✓ ' : '✗ '}{testResult.message}
                  </p>
                )}

                <div className="flex gap-2 pt-1">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => testMutation.mutate()}
                    loading={testMutation.isPending}
                  >
                    Test
                  </Button>
                  {isEditing ? (
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => updateMutation.mutate()}
                      loading={updateMutation.isPending}
                      disabled={!form.name || !form.database}
                    >
                      Save Changes
                    </Button>
                  ) : (
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => createMutation.mutate()}
                      loading={createMutation.isPending}
                      disabled={!form.name || !form.database}
                    >
                      Create Project
                    </Button>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function ProjectCard({
  project,
  isEditing,
  onOpen,
  onEdit,
  onDelete,
}: {
  project: Project
  isEditing: boolean
  onOpen: () => void
  onEdit: () => void
  onDelete: () => void
}) {
  return (
    <div
      className={cn(
        'group flex items-center gap-4 rounded border bg-surface-elevated p-4 transition-colors',
        isEditing ? 'border-accent/60' : 'border-surface-border hover:border-accent/40'
      )}
    >
      <Database className="h-8 w-8 text-text-muted group-hover:text-accent transition-colors flex-shrink-0" />
      <button className="flex-1 min-w-0 text-left" onClick={onOpen}>
        <p className="text-sm font-medium text-text-primary">{project.name}</p>
        {project.description && (
          <p className="text-xs text-text-secondary truncate">{project.description}</p>
        )}
        <p className="text-2xs text-text-muted mt-0.5">Created {formatDate(project.created_at)}</p>
      </button>
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={(e) => { e.stopPropagation(); onEdit() }}
          className="rounded p-1.5 text-text-muted hover:bg-surface-hover hover:text-text-primary transition-colors"
          title="Edit connection"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete() }}
          className="rounded p-1.5 text-text-muted hover:bg-surface-hover hover:text-status-rejected transition-colors"
          title="Delete project"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={onOpen}
          className="rounded p-1.5 text-text-muted hover:bg-surface-hover hover:text-text-primary transition-colors"
          title="Open project"
        >
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}

const inputClass =
  'w-full rounded border border-surface-border bg-surface px-2.5 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-text-secondary">{label}</label>
      {children}
    </div>
  )
}
