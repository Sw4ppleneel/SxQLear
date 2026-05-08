import React from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { RefreshCw, ChevronDown, ChevronRight, Square, Zap, Search, X, AlertCircle } from 'lucide-react'
import { getLatestSnapshot, getSchemaGraph, crawlSchema, cancelCrawl, searchColumns } from '@/lib/api'
import { SchemaGraph } from '@/components/schema/SchemaGraph'
import { Button } from '@/components/common/Button'
import { useProjectStore } from '@/stores/projectStore'
import { cn, formatRowCount } from '@/lib/utils'
import type { TableProfile, ColumnProfile, TermSearchResult } from '@/types'
import { useState, useRef } from 'react'

export function SchemaView() {
  const { projectId } = useParams<{ projectId: string }>()
  const queryClient = useQueryClient()
  const { selectedTable, setSelectedTable } = useProjectStore()

  const { data: snapshot, isLoading: snapshotLoading } = useQuery({
    queryKey: ['snapshot', projectId],
    queryFn: () => getLatestSnapshot(projectId!),
    enabled: !!projectId,
    retry: false,
  })

  const { data: graphData, isLoading: graphLoading } = useQuery({
    queryKey: ['graph', projectId],
    queryFn: () => getSchemaGraph(projectId!),
    enabled: !!projectId && !!snapshot,
  })

  const crawlMutation = useMutation({
    mutationFn: (mode: 'full' | 'quick') => crawlSchema(projectId!, { mode }),
    onSuccess: (_data, mode) => {
      queryClient.invalidateQueries({ queryKey: ['snapshot', projectId] })
      queryClient.invalidateQueries({ queryKey: ['graph', projectId] })
      toast.success(mode === 'quick' ? 'Quick scan complete' : 'Full crawl complete')
    },
    onError: () => toast.error('Crawl failed'),
  })

  const cancelMutation = useMutation({
    mutationFn: () => cancelCrawl(projectId!),
    onSuccess: () => {
      // The crawl endpoint will return once the current table finishes;
      // the crawlMutation's onSuccess fires and refreshes the snapshot.
      toast('Stopping crawl…', { icon: '⏹' })
    },
  })

  const selectedTableData = snapshot?.tables.find((t) => t.name === selectedTable) ?? null
  const isCrawling = crawlMutation.isPending

  // Column search state
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchInput, setSearchInput] = useState('')
  const [searchResults, setSearchResults] = useState<TermSearchResult[] | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const searchMutation = useMutation({
    mutationFn: (terms: string[]) => searchColumns(projectId!, terms, 5),
    onSuccess: (data) => setSearchResults(data),
    onError: () => toast.error('Search failed'),
  })

  function runSearch() {
    const terms = searchInput
      .split(/[\n,]+/)
      .map((t) => t.trim())
      .filter(Boolean)
    if (terms.length === 0) return
    searchMutation.mutate(terms)
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-surface-border px-6 py-4">
        <div>
          <h1 className="text-base font-semibold text-text-primary">Schema</h1>
          <p className="text-sm text-text-secondary">
            {snapshot
              ? `${snapshot.tables.length} tables · version ${snapshot.version}`
              : 'No schema snapshot yet'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {snapshot && (
            <Button
              variant={searchOpen ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => { setSearchOpen((o) => !o); setSearchResults(null) }}
              title="Search for concepts or variable names across all columns"
            >
              <Search className="h-3.5 w-3.5" />
              Find Columns
            </Button>
          )}
          {isCrawling ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => cancelMutation.mutate()}
              loading={cancelMutation.isPending}
            >
              <Square className="h-3.5 w-3.5" />
              Stop
            </Button>
          ) : (
            <>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => crawlMutation.mutate('quick')}
                title="Scan table names, column headers and row counts — fast"
              >
                <Zap className="h-3.5 w-3.5" />
                Quick Scan
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => crawlMutation.mutate('full')}
                title="Full profiling — null rates, cardinality, sample values"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Full Crawl
              </Button>
            </>
          )}
        </div>
      </div>

      {isCrawling && (
        <div className="flex items-center gap-2 border-b border-surface-border bg-accent/5 px-6 py-2 text-xs text-accent">
          <RefreshCw className="h-3 w-3 animate-spin" />
          Crawling schema… this may take a while for large databases.
          Click Stop to save partial results.
        </div>
      )}

      {/* Column search panel */}
      {searchOpen && snapshot && (
        <div className="border-b border-surface-border bg-surface-elevated">
          <div className="px-6 py-3 space-y-2">
            <p className="text-xs font-medium text-text-secondary">
              Enter concept or variable names — one per line or comma-separated.
              SxQLear will rank columns across all {snapshot.tables.length} tables by match score.
            </p>
            <div className="flex gap-2">
              <textarea
                ref={textareaRef}
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) runSearch() }}
                placeholder={"session_id\npatient_id\nattendance_status\ncancellation_reason\nprovider_exit_date"}
                className="flex-1 rounded border border-surface-border bg-surface px-3 py-2 font-mono text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-accent resize-none"
                rows={4}
              />
              <div className="flex flex-col gap-1.5">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={runSearch}
                  loading={searchMutation.isPending}
                >
                  <Search className="h-3.5 w-3.5" />
                  Search
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => { setSearchInput(''); setSearchResults(null) }}
                >
                  <X className="h-3.5 w-3.5" />
                  Clear
                </Button>
              </div>
            </div>
            <p className="text-2xs text-text-muted">Ctrl+Enter to search</p>
          </div>

          {searchResults && (
            <div className="max-h-64 overflow-y-auto border-t border-surface-border">
              {searchResults.map((result) => (
                <div key={result.term} className="border-b border-surface-border/50 last:border-0">
                  <div className="flex items-center gap-2 px-6 py-1.5 bg-surface">
                    <span className="font-mono text-xs font-semibold text-text-primary">{result.term}</span>
                    <span className="text-2xs text-text-muted">{result.matches.length} matches</span>
                  </div>
                  {result.matches.length === 0 ? (
                    <div className="flex items-center gap-1.5 px-6 py-2 text-2xs text-text-muted">
                      <AlertCircle className="h-3 w-3" />
                      No matching columns found
                    </div>
                  ) : (
                    <div className="divide-y divide-surface-border/30">
                      {result.matches.map((m, i) => (
                        <button
                          key={`${m.table}.${m.column}`}
                          onClick={() => setSelectedTable(m.table)}
                          className="flex w-full items-center gap-3 px-6 py-1.5 text-left hover:bg-surface-hover transition-colors"
                        >
                          <span className="w-5 text-right text-2xs text-text-muted">{i + 1}</span>
                          <div className="flex-1 min-w-0">
                            <span className="font-mono text-xs text-accent">{m.table}</span>
                            <span className="text-text-muted text-xs">.</span>
                            <span className="font-mono text-xs text-text-primary font-medium">{m.column}</span>
                            <span className="ml-2 text-2xs text-text-muted">{m.raw_type}</span>
                          </div>
                          <span className="text-2xs text-text-muted tabular-nums">{(m.score * 100).toFixed(0)}%</span>
                          <span className="text-2xs text-text-muted truncate max-w-[180px]">{m.reasons[0]}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* Graph */}
        <div className="flex-1 overflow-hidden">
          {graphLoading || snapshotLoading ? (
            <div className="flex h-full items-center justify-center text-sm text-text-secondary">
              Loading schema…
            </div>
          ) : graphData ? (
            <SchemaGraph
              data={graphData}
              selectedTable={selectedTable}
              onTableSelect={setSelectedTable}
            />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
              <p className="text-text-secondary text-sm">No schema snapshot found</p>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => crawlMutation.mutate('quick')}
                  loading={isCrawling}
                >
                  <Zap className="h-3.5 w-3.5" />
                  Quick Scan
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => crawlMutation.mutate('full')}
                  loading={isCrawling}
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  Full Crawl
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Table browser */}
        {snapshot && (
          <div className="w-64 flex-shrink-0 overflow-y-auto border-l border-surface-border bg-surface-elevated">
            <div className="border-b border-surface-border px-3 py-2">
              <p className="text-xs font-medium text-text-secondary">Tables</p>
            </div>
            <div>
              {snapshot.tables.map((table) => (
                <TableListItem
                  key={table.name}
                  table={table}
                  isSelected={selectedTable === table.name}
                  onClick={() => setSelectedTable(table.name === selectedTable ? null : table.name)}
                />
              ))}
            </div>
          </div>
        )}

        {/* Column detail panel */}
        {selectedTableData && (
          <div className="w-72 flex-shrink-0 overflow-y-auto border-l border-surface-border bg-surface">
            <div className="border-b border-surface-border px-4 py-2">
              <p className="font-mono text-sm font-semibold text-text-primary">
                {selectedTableData.name}
              </p>
              <p className="text-xs text-text-muted">
                {formatRowCount(selectedTableData.row_count ?? undefined)} rows
              </p>
            </div>
            <div>
              {selectedTableData.columns.map((col) => (
                <ColumnRow key={col.name} column={col} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function TableListItem({
  table,
  isSelected,
  onClick,
}: {
  table: TableProfile
  isSelected: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors',
        isSelected
          ? 'bg-accent/10 text-accent'
          : 'text-text-secondary hover:bg-surface-hover hover:text-text-primary'
      )}
    >
      {isSelected ? (
        <ChevronDown className="h-3 w-3 flex-shrink-0" />
      ) : (
        <ChevronRight className="h-3 w-3 flex-shrink-0" />
      )}
      <span className="flex-1 truncate font-mono">{table.name}</span>
      <span className="text-text-muted">{table.columns.length}</span>
    </button>
  )
}

function ColumnRow({ column }: { column: ColumnProfile }) {
  const isPk = column.is_primary_key
  const isFk = column.is_foreign_key
  return (
    <div className="border-b border-surface-border/50 px-4 py-2">
      <div className="flex items-center gap-1.5">
        {isPk && <span className="text-2xs text-amber-400">PK</span>}
        {isFk && <span className="text-2xs text-blue-400">FK</span>}
        <span className={cn('font-mono text-xs', isPk ? 'text-text-primary font-medium' : 'text-text-secondary')}>
          {column.name}
        </span>
      </div>
      <p className="mt-0.5 text-2xs text-text-muted">
        {column.raw_type}
        {column.is_nullable ? ' · nullable' : ' · not null'}
      </p>
      {column.sample_values && column.sample_values.length > 0 && (
        <p className="mt-0.5 truncate text-2xs text-text-muted">
          eg: {column.sample_values.slice(0, 3).map(String).join(', ')}
        </p>
      )}
    </div>
  )
}
