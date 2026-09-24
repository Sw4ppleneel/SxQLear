import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  AlertCircle, ArrowLeft, ArrowRight, BarChart2, ChevronDown, ChevronRight,
  Columns3, Database, GitBranch, List, Network, RefreshCw, Search,
  Square, X, Zap,
} from 'lucide-react'
import {
  cancelCrawl, crawlSchema, getCrawlJob, getLatestSnapshot, getSchemaGraph,
  profileColumn, searchColumns,
} from '@/lib/api'
import { SchemaGraph } from '@/components/schema/SchemaGraph'
import { Button } from '@/components/common/Button'
import { useProjectStore } from '@/stores/projectStore'
import { cn, formatRowCount } from '@/lib/utils'
import type { ColumnProfile, ColumnProfileResult, CrawlJobStatus, TermSearchResult } from '@/types'

const TERMINAL_STATUSES: CrawlJobStatus[] = ['completed', 'cancelled', 'failed']
type ViewMode = 'browse' | 'map'
type FieldFilter = 'all' | 'keys' | 'nullable'

export function SchemaView() {
  const { projectId } = useParams<{ projectId: string }>()
  const queryClient = useQueryClient()
  const { selectedTable, setSelectedTable } = useProjectStore()
  const [viewMode, setViewMode] = useState<ViewMode>('browse')
  const [tableFilter, setTableFilter] = useState('')
  const [fieldFilter, setFieldFilter] = useState('')
  const [fieldScope, setFieldScope] = useState<FieldFilter>('all')
  const [searchInput, setSearchInput] = useState('')
  const [searchResult, setSearchResult] = useState<TermSearchResult | null>(null)
  const [highlightedColumn, setHighlightedColumn] = useState<string | null>(null)
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [activeMode, setActiveMode] = useState<'full' | 'quick' | null>(null)

  const { data: snapshot, isLoading: snapshotLoading } = useQuery({
    queryKey: ['snapshot', projectId],
    queryFn: () => getLatestSnapshot(projectId!),
    enabled: !!projectId,
    retry: false,
  })

  const { data: graphData, isLoading: graphLoading } = useQuery({
    queryKey: ['graph', projectId],
    queryFn: () => getSchemaGraph(projectId!),
    enabled: !!projectId && !!snapshot && viewMode === 'map',
  })

  const crawlMutation = useMutation({
    mutationFn: (mode: 'full' | 'quick') => crawlSchema(projectId!, { mode }),
    onSuccess: (job, mode) => { setActiveJobId(job.job_id); setActiveMode(mode) },
    onError: () => toast.error('Could not start the scan'),
  })

  const jobQuery = useQuery({
    queryKey: ['crawl-job', projectId, activeJobId],
    queryFn: () => getCrawlJob(projectId!, activeJobId!),
    enabled: !!projectId && !!activeJobId,
    refetchInterval: query => {
      const status = query.state.data?.status
      return status && TERMINAL_STATUSES.includes(status) ? false : 1500
    },
  })

  useEffect(() => {
    const status = jobQuery.data?.status
    if (!status || !TERMINAL_STATUSES.includes(status)) return
    queryClient.invalidateQueries({ queryKey: ['snapshot', projectId] })
    queryClient.invalidateQueries({ queryKey: ['graph', projectId] })
    if (status === 'completed') toast.success(activeMode === 'quick' ? 'Quick scan complete' : 'Full crawl complete')
    if (status === 'cancelled') toast('Scan stopped. Partial results were saved.')
    if (status === 'failed') toast.error(jobQuery.data?.error ?? 'Scan failed')
    setActiveJobId(null)
    setActiveMode(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobQuery.data?.status])

  const cancelMutation = useMutation({
    mutationFn: () => cancelCrawl(projectId!, activeJobId!),
    onSuccess: () => toast('Stopping scan…'),
  })

  const searchMutation = useMutation({
    mutationFn: (query: string) => searchColumns(projectId!, [query], 12),
    onSuccess: results => { setSearchResult(results[0] ?? null); setViewMode('browse') },
    onError: () => toast.error('Search failed'),
  })

  const tables = snapshot?.tables ?? []
  const totalColumns = useMemo(() => tables.reduce((count, table) => count + table.columns.length, 0), [tables])
  const visibleTables = useMemo(() => {
    const query = tableFilter.trim().toLowerCase()
    return tables
      .filter(table => !query || table.name.toLowerCase().includes(query) ||
        table.columns.some(column => column.name.toLowerCase().includes(query)))
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [tables, tableFilter])
  const currentTable = tables.find(table => table.name === selectedTable) ?? tables[0] ?? null
  const visibleColumns = useMemo(() => {
    if (!currentTable) return []
    const query = fieldFilter.trim().toLowerCase()
    return currentTable.columns.filter(column =>
      (!query || column.name.toLowerCase().includes(query) || column.raw_type.toLowerCase().includes(query)) &&
      (fieldScope === 'all' || (fieldScope === 'keys' && (column.is_primary_key || column.is_foreign_key)) ||
        (fieldScope === 'nullable' && column.is_nullable))
    )
  }, [currentTable, fieldFilter, fieldScope])

  useEffect(() => {
    if (!highlightedColumn || searchResult || viewMode !== 'browse') return
    const frame = requestAnimationFrame(() => {
      document.getElementById(`column-${encodeURIComponent(highlightedColumn)}`)?.scrollIntoView({ block: 'center' })
    })
    return () => cancelAnimationFrame(frame)
  }, [highlightedColumn, currentTable?.name, searchResult, viewMode])

  const isCrawling = crawlMutation.isPending || !!activeJobId

  function openTable(tableName: string, columnName?: string) {
    setSelectedTable(tableName)
    setHighlightedColumn(columnName ?? null)
    setSearchResult(null)
    setTableFilter('')
    setFieldFilter('')
    setFieldScope('all')
    setViewMode('browse')
  }

  function runSearch(event: React.FormEvent) {
    event.preventDefault()
    const query = searchInput.trim()
    if (query) searchMutation.mutate(query)
  }

  return (
    <div className="flex h-full min-w-0 flex-col overflow-hidden bg-surface">
      <header className="shrink-0 border-b border-surface-border px-4 py-4 sm:px-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="mb-1 text-2xs font-semibold uppercase tracking-[0.16em] text-accent">Data catalog</p>
            <h1 className="text-xl font-semibold tracking-tight text-text-primary">Explore your schema</h1>
            <p className="mt-1 text-xs text-text-secondary">
              {snapshot ? `${tables.length} tables · ${totalColumns} columns · snapshot ${snapshot.version}` : 'Discover the tables and fields in your database'}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {isCrawling ? (
              <Button variant="secondary" size="sm" className="min-h-11" onClick={() => cancelMutation.mutate()} loading={cancelMutation.isPending}>
                <Square className="h-3.5 w-3.5" /> Stop scan
              </Button>
            ) : (
              <>
                <Button variant="secondary" size="sm" className="min-h-11" onClick={() => crawlMutation.mutate('quick')} title="Read tables, columns, keys, and estimated row counts">
                  <Zap className="h-3.5 w-3.5" /> Quick scan
                </Button>
                <Button variant="secondary" size="sm" className="min-h-11" onClick={() => crawlMutation.mutate('full')} title="Also profile column values and statistics">
                  <RefreshCw className="h-3.5 w-3.5" /> Full crawl
                </Button>
              </>
            )}
          </div>
        </div>

        {snapshot && (
          <div className="mt-5 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <form onSubmit={runSearch} className="flex min-w-0 flex-1 items-center gap-2 lg:max-w-2xl">
              <div className="flex h-11 min-w-0 flex-1 items-center gap-2 rounded-lg border border-surface-border bg-surface-elevated px-3 focus-within:border-accent/60">
                <Search className="h-4 w-4 shrink-0 text-text-muted" />
                <input
                  value={searchInput}
                  onChange={event => setSearchInput(event.target.value)}
                  placeholder="Ask where a field lives, e.g. customer renewal date"
                  aria-label="Search fields across all tables"
                  className="min-w-0 flex-1 bg-transparent text-sm text-text-primary outline-none placeholder:text-text-muted"
                />
                {searchInput && <button type="button" onClick={() => { setSearchInput(''); setSearchResult(null) }} aria-label="Clear search" className="rounded p-1 text-text-muted hover:text-text-primary"><X className="h-4 w-4" /></button>}
              </div>
              <Button variant="primary" size="sm" className="min-h-11" loading={searchMutation.isPending} type="submit">Search</Button>
            </form>
            <div className="flex rounded-lg border border-surface-border bg-surface-elevated p-1" aria-label="Schema view">
              <button onClick={() => setViewMode('browse')} className={cn('flex min-h-11 items-center gap-2 rounded-md px-3 text-xs font-medium', viewMode === 'browse' ? 'bg-surface-overlay text-text-primary' : 'text-text-secondary hover:text-text-primary')} aria-pressed={viewMode === 'browse'}>
                <List className="h-3.5 w-3.5" /> Browse
              </button>
              <button onClick={() => { setSearchResult(null); setViewMode('map') }} className={cn('flex min-h-11 items-center gap-2 rounded-md px-3 text-xs font-medium', viewMode === 'map' ? 'bg-surface-overlay text-text-primary' : 'text-text-secondary hover:text-text-primary')} aria-pressed={viewMode === 'map'}>
                <Network className="h-3.5 w-3.5" /> Map
              </button>
            </div>
          </div>
        )}
      </header>

      {isCrawling && <CrawlProgress job={jobQuery.data} />}

      {snapshotLoading ? (
        <div className="flex flex-1 items-center justify-center text-sm text-text-secondary">Loading schema…</div>
      ) : !snapshot ? (
        <div className="flex flex-1 items-center justify-center p-6">
          <div className="max-w-md rounded-xl border border-surface-border bg-surface-elevated p-8 text-center">
            <Database className="mx-auto mb-4 h-9 w-9 text-accent" />
            <h2 className="text-base font-semibold text-text-primary">Start with a schema scan</h2>
            <p className="mt-2 text-sm leading-6 text-text-secondary">A quick scan reads table names, columns, and key relationships so you can browse and search them here.</p>
            <div className="mt-5 flex justify-center gap-2">
              <Button variant="primary" size="sm" onClick={() => crawlMutation.mutate('quick')} loading={isCrawling}><Zap className="h-3.5 w-3.5" /> Quick scan</Button>
              <Button variant="secondary" size="sm" onClick={() => crawlMutation.mutate('full')} loading={isCrawling}>Full crawl</Button>
            </div>
          </div>
        </div>
      ) : viewMode === 'map' ? (
        <div className="min-h-0 flex-1">
          {graphLoading || !graphData ? <div className="flex h-full items-center justify-center text-sm text-text-secondary">Loading relationship map…</div> :
            <SchemaGraph data={graphData} selectedTable={currentTable?.name} onTableSelect={table => openTable(table)} />}
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          <aside className="flex max-h-44 shrink-0 flex-col border-b border-surface-border bg-surface-elevated md:max-h-none md:w-64 md:border-b-0 md:border-r xl:w-72">
            <div className="border-b border-surface-border p-3">
              <div className="mb-2 flex items-center justify-between"><h2 className="text-xs font-semibold text-text-primary">Tables</h2><span className="text-2xs text-text-muted">{visibleTables.length} / {tables.length}</span></div>
              <div className="flex h-9 items-center gap-2 rounded-md border border-surface-border bg-surface px-2.5">
                <Search className="h-3.5 w-3.5 shrink-0 text-text-muted" />
                <input value={tableFilter} onChange={event => setTableFilter(event.target.value)} placeholder="Filter tables or columns" aria-label="Filter table list" className="min-w-0 flex-1 bg-transparent text-xs text-text-primary outline-none placeholder:text-text-muted" />
              </div>
            </div>
            <div className="overflow-y-auto p-1.5">
              {visibleTables.length ? visibleTables.map(table => (
                <button key={table.name} onClick={() => openTable(table.name, tableFilter && !table.name.toLowerCase().includes(tableFilter.toLowerCase()) ? table.columns.find(column => column.name.toLowerCase().includes(tableFilter.toLowerCase()))?.name : undefined)} className={cn('mb-0.5 flex min-h-11 w-full items-center gap-2 rounded-md px-2.5 text-left transition-colors', currentTable?.name === table.name && !searchResult ? 'bg-accent/15 text-accent' : 'text-text-secondary hover:bg-surface-hover hover:text-text-primary')}>
                  <Database className="h-4 w-4 shrink-0 opacity-70" />
                  <span className="min-w-0 flex-1 truncate font-mono text-xs" title={table.name}>{table.name}</span>
                  <span className="text-2xs tabular-nums opacity-60">{table.columns.length}</span>
                </button>
              )) : <p className="px-3 py-4 text-xs text-text-muted">No tables match this filter.</p>}
            </div>
          </aside>

          <main className="min-h-0 min-w-0 flex-1 overflow-y-auto">
            {searchResult ? (
              <SearchResults result={searchResult} onOpen={openTable} onBack={() => setSearchResult(null)} />
            ) : currentTable ? (
              <div className="mx-auto max-w-5xl px-4 py-5 sm:px-6 lg:px-8">
                <div className="flex flex-wrap items-start justify-between gap-3 border-b border-surface-border pb-5">
                  <div className="min-w-0">
                    <p className="mb-1 text-2xs font-semibold uppercase tracking-widest text-text-muted">Table</p>
                    <h2 className="break-all font-mono text-xl font-semibold text-text-primary">{currentTable.name}</h2>
                    {currentTable.analyst_note && !currentTable.analyst_note.includes('pending — catalog stage only') && <p className="mt-2 text-xs text-text-secondary">{currentTable.analyst_note}</p>}
                  </div>
                  <div className="flex gap-4 text-xs text-text-secondary">
                    <span><strong className="block text-base font-semibold text-text-primary">{formatRowCount(currentTable.row_count ?? undefined)}</strong>rows</span>
                    <span><strong className="block text-base font-semibold text-text-primary">{currentTable.columns.length}</strong>columns</span>
                  </div>
                </div>

                {currentTable.foreign_key_constraints.length > 0 && (
                  <div className="mt-5 rounded-lg border border-surface-border bg-surface-elevated p-4">
                    <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-text-primary"><GitBranch className="h-4 w-4 text-accent" /> Relationships</div>
                    <div className="flex flex-wrap gap-2">
                      {currentTable.foreign_key_constraints.map((fk, index) => (
                        <button key={`${fk.referred_table}-${index}`} onClick={() => openTable(fk.referred_table)} className="flex min-h-9 items-center gap-1.5 rounded-md border border-surface-border px-2.5 text-left font-mono text-2xs text-text-secondary hover:border-accent/50 hover:text-accent">
                          {fk.constrained_columns.join(', ')} <ArrowRight className="h-3 w-3 shrink-0" /> {fk.referred_table}.{fk.referred_columns.join(', ')}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
                  <div><h3 className="text-sm font-semibold text-text-primary">Columns</h3><p className="mt-0.5 text-2xs text-text-muted">Select a column for a live profile</p></div>
                  <div className="flex flex-wrap gap-2">
                    <div className="flex h-9 items-center gap-2 rounded-md border border-surface-border bg-surface-elevated px-2.5">
                      <Search className="h-3.5 w-3.5 text-text-muted" />
                      <input value={fieldFilter} onChange={event => setFieldFilter(event.target.value)} placeholder="Filter columns" aria-label="Filter columns in table" className="w-32 bg-transparent text-xs text-text-primary outline-none placeholder:text-text-muted sm:w-40" />
                    </div>
                    <select value={fieldScope} onChange={event => setFieldScope(event.target.value as FieldFilter)} aria-label="Column type filter" className="h-9 rounded-md border border-surface-border bg-surface-elevated px-2 text-xs text-text-secondary outline-none focus:border-accent">
                      <option value="all">All fields</option><option value="keys">Keys only</option><option value="nullable">Nullable only</option>
                    </select>
                  </div>
                </div>

                <div className="mt-3 overflow-hidden rounded-lg border border-surface-border bg-surface-elevated">
                  <div className="hidden grid-cols-[minmax(0,1fr)_minmax(7rem,10rem)_7rem_5rem] gap-3 border-b border-surface-border bg-surface-overlay px-4 py-2 text-2xs font-semibold uppercase tracking-wider text-text-muted sm:grid">
                    <span>Column</span><span>Type</span><span>Constraint</span><span></span>
                  </div>
                  {visibleColumns.length ? visibleColumns.map(column => (
                    <ColumnRow key={`${currentTable.name}.${column.name}`} column={column} tableName={currentTable.name} projectId={projectId!} highlighted={highlightedColumn === column.name} />
                  )) : <div className="px-4 py-10 text-center text-sm text-text-muted">No columns match these filters.</div>}
                </div>
                <p className="mt-2 text-right text-2xs text-text-muted">Showing {visibleColumns.length} of {currentTable.columns.length} columns</p>
              </div>
            ) : <div className="flex h-full items-center justify-center text-sm text-text-muted">No tables in this snapshot.</div>}
          </main>
        </div>
      )}
    </div>
  )
}

function CrawlProgress({ job }: { job?: { current_stage: string | null; stages: Record<string, { done: number; total: number }> } }) {
  const stage = job?.current_stage
  const progress = stage ? job?.stages[stage] : null
  const labels: Record<string, string> = { catalog: 'Reading schema', cheap_stats: 'Estimating rows', sampled_profiling: 'Profiling columns', sample_values: 'Profiling values' }
  return <div className="flex shrink-0 items-center gap-2 border-b border-surface-border bg-accent/5 px-4 py-2 text-xs text-accent sm:px-6"><RefreshCw className="h-3.5 w-3.5 animate-spin" />{stage ? labels[stage] ?? stage : 'Starting scan'}{progress ? ` · ${progress.done}/${progress.total} tables` : '…'}</div>
}

function SearchResults({ result, onOpen, onBack }: { result: TermSearchResult; onOpen: (table: string, column?: string) => void; onBack: () => void }) {
  return <div className="mx-auto max-w-4xl px-4 py-5 sm:px-6 lg:px-8">
    <button onClick={onBack} className="mb-4 flex min-h-9 items-center gap-1.5 text-xs text-text-secondary hover:text-text-primary"><ArrowLeft className="h-3.5 w-3.5" /> Back to table</button>
    <div className="mb-5 flex flex-wrap items-end justify-between gap-2"><div><p className="text-2xs font-semibold uppercase tracking-widest text-accent">Field search</p><h2 className="mt-1 text-lg font-semibold text-text-primary">Results for “{result.term}”</h2></div><span className="text-xs text-text-muted">{result.matches.length} matches · {result.search_mode === 'hybrid' ? 'semantic + name' : 'name'} ranking</span></div>
    {result.matches.length ? <div className="space-y-2">{result.matches.map(match => (
      <button key={`${match.table}.${match.column}`} onClick={() => onOpen(match.table, match.column)} className="flex min-h-20 w-full items-center gap-3 rounded-lg border border-surface-border bg-surface-elevated px-4 py-3 text-left transition-colors hover:border-accent/50 hover:bg-surface-hover">
        <Columns3 className="h-4 w-4 shrink-0 text-accent" />
        <span className="min-w-0 flex-1"><span className="block truncate font-mono text-sm text-text-primary">{match.table}<span className="text-text-muted">.</span>{match.column}</span><span className="mt-1 block truncate text-xs text-text-secondary">{match.raw_type} · {match.reasons.join(' · ')}</span></span>
        <span className="hidden text-2xs tabular-nums text-text-muted sm:block">{Math.round(match.score * 100)} relevance</span><ChevronRight className="h-4 w-4 shrink-0 text-text-muted" />
      </button>
    ))}</div> : <div className="rounded-lg border border-surface-border bg-surface-elevated p-8 text-center text-sm text-text-secondary"><AlertCircle className="mx-auto mb-2 h-5 w-5" />No matching columns. Try a table name, field name, or a shorter concept.</div>}
  </div>
}

function ColumnRow({ column, tableName, projectId, highlighted }: { column: ColumnProfile; tableName: string; projectId: string; highlighted: boolean }) {
  const [open, setOpen] = useState(false)
  const [profile, setProfile] = useState<ColumnProfileResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function toggleProfile() {
    if (open) { setOpen(false); return }
    setOpen(true)
    if (profile) return
    setLoading(true)
    setError(null)
    try { setProfile(await profileColumn(projectId, tableName, column.name)) }
    catch (failure: unknown) {
      const message = (failure as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(message ?? 'Could not load the live profile')
    } finally { setLoading(false) }
  }

  return <div id={`column-${encodeURIComponent(column.name)}`} className={cn('border-b border-surface-border/70 last:border-b-0', highlighted && 'bg-accent/10')}>
    <button onClick={toggleProfile} aria-expanded={open} className="grid min-h-14 w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-4 py-2 text-left hover:bg-surface-hover sm:grid-cols-[minmax(0,1fr)_minmax(7rem,10rem)_7rem_5rem]">
      <span className="min-w-0"><span className="block truncate font-mono text-xs font-medium text-text-primary" title={column.name}>{column.name}</span>{column.analyst_note && <span className="mt-1 block truncate text-2xs text-text-muted">{column.analyst_note}</span>}</span>
      <span className="hidden truncate font-mono text-2xs text-text-secondary sm:block" title={column.raw_type}>{column.raw_type}</span>
      <span className="hidden flex-wrap gap-1 sm:flex">{column.is_primary_key && <span className="rounded bg-amber-400/10 px-1.5 py-0.5 text-2xs text-amber-400">PK</span>}{column.is_foreign_key && <span className="rounded bg-blue-400/10 px-1.5 py-0.5 text-2xs text-blue-400">FK</span>}{!column.is_primary_key && !column.is_foreign_key && <span className="text-2xs text-text-muted">{column.is_nullable ? 'Nullable' : 'Required'}</span>}</span>
      <span className="flex items-center gap-1 text-2xs text-text-muted"><BarChart2 className="h-3.5 w-3.5" />{open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}</span>
      <span className="col-span-2 -mt-2 text-2xs text-text-muted sm:hidden">{column.raw_type}{column.is_primary_key ? ' · PK' : column.is_foreign_key ? ' · FK' : column.is_nullable ? ' · nullable' : ' · required'}</span>
    </button>
    {open && <div className="border-t border-surface-border bg-surface px-4 py-4">
      {column.is_foreign_key && column.referenced_table && <p className="mb-3 text-xs text-text-secondary">References <span className="font-mono text-accent">{column.referenced_table}.{column.referenced_column ?? 'key'}</span></p>}
      {loading && <p className="text-xs text-text-muted">Loading live profile…</p>}
      {error && <p className="text-xs text-status-rejected">{error}</p>}
      {profile && <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Rows" value={profile.total_rows.toLocaleString()} />
        <Metric label="Non-null" value={profile.non_null_count.toLocaleString()} />
        <Metric label="Null" value={`${profile.null_count.toLocaleString()} (${profile.null_pct}%)`} />
        <Metric label="Distinct" value={profile.distinct_count.toLocaleString()} />
        {profile.kind === 'numeric' && <><Metric label="Min" value={profile.min} /><Metric label="Median" value={profile.median} /><Metric label="Mean" value={profile.mean} /><Metric label="Max" value={profile.max} /></>}
        {profile.kind === 'categorical' && profile.top_values && profile.top_values.length > 0 && <div className="sm:col-span-2 lg:col-span-4"><p className="mb-2 text-2xs font-semibold uppercase tracking-wider text-text-muted">Top values</p><div className="flex flex-wrap gap-2">{profile.top_values.slice(0, 8).map(value => <span key={value.value} className="max-w-full truncate rounded border border-surface-border px-2 py-1 font-mono text-2xs text-text-secondary" title={value.value}>{value.value} <span className="text-text-muted">{value.share_pct}%</span></span>)}</div></div>}
      </div>}
    </div>}
  </div>
}

function Metric({ label, value }: { label: string; value: number | string | null | undefined }) {
  return <div className="rounded-md border border-surface-border bg-surface-elevated px-3 py-2"><p className="text-2xs text-text-muted">{label}</p><p className="mt-1 truncate font-mono text-xs text-text-primary">{value ?? '—'}</p></div>
}
