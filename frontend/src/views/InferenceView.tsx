import React from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Play, SlidersHorizontal, Plus, Sparkles, X, Check, ChevronDown, ChevronRight } from 'lucide-react'
import {
  runInference,
  getRelationships,
  createManualRelationship,
  suggestRelationships,
  getLatestSnapshot,
} from '@/lib/api'
import { RelationshipCard } from '@/components/inference/RelationshipCard'
import { Button } from '@/components/common/Button'
import { ConfidenceBadge } from '@/components/common/Badges'
import type {
  InferredRelationship,
  ConfidenceTier,
  ManualRelationshipRequest,
  SuggestedJoin,
  TableProfile,
} from '@/types'
import { cn } from '@/lib/utils'

const TIERS: ConfidenceTier[] = ['certain', 'high', 'medium', 'low', 'speculative']
const REL_TYPES = ['many-to-one', 'one-to-one', 'many-to-many'] as const

export function InferenceView() {
  const { projectId } = useParams<{ projectId: string }>()
  const queryClient = useQueryClient()
  const [filterTier, setFilterTier] = React.useState<ConfidenceTier | null>(null)
  const [useStatistical, setUseStatistical] = React.useState(false)

  // Manual relationship modal state
  const [showManual, setShowManual] = React.useState(false)
  const [manualForm, setManualForm] = React.useState<ManualRelationshipRequest>({
    source_table: '',
    source_column: '',
    target_table: '',
    target_column: '',
    relationship_type: 'many-to-one',
    reason: '',
  })

  // AI suggest panel state
  const [showAI, setShowAI] = React.useState(false)
  const [aiIntent, setAiIntent] = React.useState('')
  const [aiResults, setAiResults] = React.useState<SuggestedJoin[] | null>(null)
  const [aiSummary, setAiSummary] = React.useState('')
  const [aiModel, setAiModel] = React.useState('')
  const [acceptedSuggestions, setAcceptedSuggestions] = React.useState<Set<number>>(new Set())
  const [rejectedSuggestions, setRejectedSuggestions] = React.useState<Set<number>>(new Set())

  const { data: snapshot } = useQuery({
    queryKey: ['snapshot', projectId],
    queryFn: () => getLatestSnapshot(projectId!),
    enabled: !!projectId,
    retry: false,
  })

  const { data: relationships = [], isLoading } = useQuery({
    queryKey: ['relationships', projectId],
    queryFn: () => getRelationships(projectId!),
    enabled: !!projectId,
  })

  const tables: TableProfile[] = snapshot?.tables ?? []

  const inferMutation = useMutation({
    mutationFn: () => runInference(projectId!, useStatistical),
    onSuccess: (results) => {
      queryClient.setQueryData(['relationships', projectId], results)
      toast.success(`Inferred ${results.length} relationships`)
    },
    onError: () => toast.error('Inference failed. Make sure a schema snapshot exists.'),
  })

  const manualMutation = useMutation({
    mutationFn: (req: ManualRelationshipRequest) => createManualRelationship(projectId!, req),
    onSuccess: (rel) => {
      queryClient.invalidateQueries({ queryKey: ['relationships', projectId] })
      queryClient.invalidateQueries({ queryKey: ['memory', projectId] })
      toast.success(`Manual relationship saved and confirmed`)
      setShowManual(false)
      setManualForm({ source_table: '', source_column: '', target_table: '', target_column: '', relationship_type: 'many-to-one', reason: '' })
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || 'Failed to save relationship'),
  })

  const suggestMutation = useMutation({
    mutationFn: () => suggestRelationships(projectId!, aiIntent),
    onSuccess: (res) => {
      setAiResults(res.suggestions)
      setAiSummary(res.llm_summary)
      setAiModel(res.model_used)
      setAcceptedSuggestions(new Set())
      setRejectedSuggestions(new Set())
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || 'AI suggestion failed'),
  })

  const acceptSuggestionMutation = useMutation({
    mutationFn: (s: SuggestedJoin) => createManualRelationship(projectId!, {
      source_table: s.source_table,
      source_column: s.source_column,
      target_table: s.target_table,
      target_column: s.target_column,
      relationship_type: s.relationship_type as any,
      reason: `AI suggestion: ${s.reasoning}`,
    }),
    onSuccess: (_, __, ctx) => {
      queryClient.invalidateQueries({ queryKey: ['relationships', projectId] })
      queryClient.invalidateQueries({ queryKey: ['memory', projectId] })
    },
  })

  const filtered = filterTier
    ? relationships.filter((r) => r.confidence === filterTier)
    : relationships

  const countsByTier = TIERS.reduce(
    (acc, tier) => {
      acc[tier] = relationships.filter((r) => r.confidence === tier).length
      return acc
    },
    {} as Record<ConfidenceTier, number>
  )

  const srcTableObj = tables.find(t => t.name === manualForm.source_table)
  const tgtTableObj = tables.find(t => t.name === manualForm.target_table)

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-surface-border px-6 py-4">
        <div>
          <h1 className="text-base font-semibold text-text-primary">Inference</h1>
          <p className="text-sm text-text-secondary">
            {relationships.length > 0
              ? `${relationships.length} relationships inferred`
              : 'Run inference to detect relationships'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => { setShowAI(o => !o); setAiResults(null) }}
            title="Ask AI to suggest joins based on your intent"
          >
            <Sparkles className="h-3.5 w-3.5" />
            Ask AI
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setShowManual(true)}
            title="Define a relationship manually"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Manually
          </Button>
          <label className="flex items-center gap-1.5 text-xs text-text-secondary cursor-pointer ml-1">
            <input
              type="checkbox"
              checked={useStatistical}
              onChange={(e) => setUseStatistical(e.target.checked)}
              className="rounded border-surface-border bg-surface accent-accent"
            />
            Statistical
          </label>
          <Button
            variant="primary"
            size="sm"
            onClick={() => inferMutation.mutate()}
            loading={inferMutation.isPending}
          >
            <Play className="h-3.5 w-3.5" />
            Run Inference
          </Button>
        </div>
      </div>

      {/* Ask AI panel */}
      {showAI && (
        <div className="border-b border-surface-border bg-surface-elevated">
          <div className="px-6 py-3 space-y-2">
            <p className="text-xs font-medium text-text-secondary">
              Describe what you're trying to build. The AI will read all column headers and suggest relevant joins — including semantic ones inference can't detect.
            </p>
            <div className="flex gap-2">
              <textarea
                value={aiIntent}
                onChange={e => setAiIntent(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) suggestMutation.mutate() }}
                placeholder="e.g. I want to track session attendance, provider exit events, and which patients renewed — to study the effect of provider disruptions on patient retention"
                className="flex-1 rounded border border-surface-border bg-surface px-3 py-2 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-accent resize-none"
                rows={3}
              />
              <div className="flex flex-col gap-1.5">
                <Button variant="primary" size="sm" onClick={() => suggestMutation.mutate()} loading={suggestMutation.isPending}>
                  <Sparkles className="h-3.5 w-3.5" />
                  Suggest
                </Button>
                <Button variant="secondary" size="sm" onClick={() => { setAiResults(null); setAiIntent('') }}>
                  <X className="h-3.5 w-3.5" />
                  Clear
                </Button>
              </div>
            </div>
            <p className="text-2xs text-text-muted">Ctrl+Enter to run · Sends only table/column names and types — no data values</p>
          </div>

          {aiResults && (
            <div className="border-t border-surface-border">
              {aiSummary && (
                <div className="px-6 py-3 bg-accent/5 border-b border-surface-border">
                  <p className="text-xs text-text-secondary leading-relaxed">{aiSummary}</p>
                  <p className="mt-1 text-2xs text-text-muted">via {aiModel}</p>
                </div>
              )}
              <div className="divide-y divide-surface-border/50 max-h-72 overflow-y-auto">
                {aiResults.map((s, i) => {
                  const accepted = acceptedSuggestions.has(i)
                  const rejected = rejectedSuggestions.has(i)
                  return (
                    <div key={i} className={cn('flex items-start gap-3 px-6 py-2.5', rejected && 'opacity-40')}>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 font-mono text-xs text-text-primary">
                          <span className="text-accent">{s.source_table}</span>
                          <span className="text-text-muted">.</span>
                          <span>{s.source_column}</span>
                          <span className="mx-1 text-text-muted">→</span>
                          <span className="text-confidence-high">{s.target_table}</span>
                          <span className="text-text-muted">.</span>
                          <span>{s.target_column}</span>
                          <span className="ml-1 text-2xs text-text-muted capitalize">{s.relationship_type}</span>
                        </div>
                        <p className="mt-0.5 text-2xs text-text-muted leading-relaxed">{s.reasoning}</p>
                      </div>
                      <div className="flex items-center gap-1 flex-shrink-0">
                        <span className={cn('text-2xs px-1.5 py-0.5 rounded', {
                          'bg-status-confirmed/15 text-status-confirmed': s.confidence === 'certain' || s.confidence === 'high',
                          'bg-amber-500/15 text-amber-400': s.confidence === 'medium',
                          'bg-surface-overlay text-text-muted': s.confidence === 'low' || s.confidence === 'speculative',
                        })}>{s.confidence}</span>
                        {!accepted && !rejected && (
                          <>
                            <button
                              onClick={() => {
                                setAcceptedSuggestions(prev => new Set([...prev, i]))
                                acceptSuggestionMutation.mutate(s)
                                toast.success('Relationship confirmed')
                              }}
                              className="ml-1 rounded p-1 text-status-confirmed hover:bg-status-confirmed/10 transition-colors"
                              title="Accept — add as confirmed relationship"
                            >
                              <Check className="h-3.5 w-3.5" />
                            </button>
                            <button
                              onClick={() => setRejectedSuggestions(prev => new Set([...prev, i]))}
                              className="rounded p-1 text-status-rejected hover:bg-status-rejected/10 transition-colors"
                              title="Dismiss"
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </>
                        )}
                        {accepted && <span className="ml-1 text-2xs text-status-confirmed">✓ added</span>}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Manual relationship modal */}
      {showManual && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-lg rounded-lg border border-surface-border bg-surface shadow-2xl">
            <div className="flex items-center justify-between border-b border-surface-border px-5 py-4">
              <div>
                <h2 className="text-sm font-semibold text-text-primary">Define Relationship Manually</h2>
                <p className="text-xs text-text-muted mt-0.5">Goes straight to confirmed — you are the authority</p>
              </div>
              <button onClick={() => setShowManual(false)} className="text-text-muted hover:text-text-primary">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              {/* Source */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-2xs font-medium text-text-secondary uppercase tracking-wide">Source Table</label>
                  <select
                    value={manualForm.source_table}
                    onChange={e => setManualForm(f => ({ ...f, source_table: e.target.value, source_column: '' }))}
                    className="w-full rounded border border-surface-border bg-surface-elevated px-2 py-1.5 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
                  >
                    <option value="">Select table…</option>
                    {tables.map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-2xs font-medium text-text-secondary uppercase tracking-wide">Source Column</label>
                  <select
                    value={manualForm.source_column}
                    onChange={e => setManualForm(f => ({ ...f, source_column: e.target.value }))}
                    disabled={!manualForm.source_table}
                    className="w-full rounded border border-surface-border bg-surface-elevated px-2 py-1.5 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-40"
                  >
                    <option value="">Select column…</option>
                    {srcTableObj?.columns.map(c => <option key={c.name} value={c.name}>{c.name} ({c.raw_type})</option>)}
                  </select>
                </div>
              </div>

              <div className="flex items-center gap-2 text-xs text-text-muted">
                <div className="flex-1 h-px bg-surface-border" />
                <span>joins to</span>
                <div className="flex-1 h-px bg-surface-border" />
              </div>

              {/* Target */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-2xs font-medium text-text-secondary uppercase tracking-wide">Target Table</label>
                  <select
                    value={manualForm.target_table}
                    onChange={e => setManualForm(f => ({ ...f, target_table: e.target.value, target_column: '' }))}
                    className="w-full rounded border border-surface-border bg-surface-elevated px-2 py-1.5 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
                  >
                    <option value="">Select table…</option>
                    {tables.map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-2xs font-medium text-text-secondary uppercase tracking-wide">Target Column</label>
                  <select
                    value={manualForm.target_column}
                    onChange={e => setManualForm(f => ({ ...f, target_column: e.target.value }))}
                    disabled={!manualForm.target_table}
                    className="w-full rounded border border-surface-border bg-surface-elevated px-2 py-1.5 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-40"
                  >
                    <option value="">Select column…</option>
                    {tgtTableObj?.columns.map(c => <option key={c.name} value={c.name}>{c.name} ({c.raw_type})</option>)}
                  </select>
                </div>
              </div>

              {/* Relationship type */}
              <div>
                <label className="mb-1 block text-2xs font-medium text-text-secondary uppercase tracking-wide">Relationship Type</label>
                <div className="flex gap-2">
                  {REL_TYPES.map(t => (
                    <button
                      key={t}
                      onClick={() => setManualForm(f => ({ ...f, relationship_type: t }))}
                      className={cn(
                        'rounded border px-2.5 py-1 text-2xs transition-colors',
                        manualForm.relationship_type === t
                          ? 'border-accent bg-accent/10 text-accent'
                          : 'border-surface-border text-text-muted hover:text-text-secondary'
                      )}
                    >{t}</button>
                  ))}
                </div>
              </div>

              {/* Reason */}
              <div>
                <label className="mb-1 block text-2xs font-medium text-text-secondary uppercase tracking-wide">Reason <span className="text-text-muted">(optional)</span></label>
                <input
                  type="text"
                  value={manualForm.reason || ''}
                  onChange={e => setManualForm(f => ({ ...f, reason: e.target.value }))}
                  placeholder="e.g. consult_id maps to consultation_id — different naming convention"
                  className="w-full rounded border border-surface-border bg-surface-elevated px-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 border-t border-surface-border px-5 py-3">
              <Button variant="secondary" size="sm" onClick={() => setShowManual(false)}>Cancel</Button>
              <Button
                variant="primary"
                size="sm"
                loading={manualMutation.isPending}
                onClick={() => manualMutation.mutate(manualForm)}
                disabled={!manualForm.source_table || !manualForm.source_column || !manualForm.target_table || !manualForm.target_column}
              >
                <Check className="h-3.5 w-3.5" />
                Confirm Relationship
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Tier filter */}
      {relationships.length > 0 && (
        <div className="flex items-center gap-2 border-b border-surface-border px-6 py-2">
          <SlidersHorizontal className="h-3.5 w-3.5 text-text-muted" />
          <button
            onClick={() => setFilterTier(null)}
            className={cn(
              'rounded px-2 py-0.5 text-xs transition-colors',
              filterTier === null
                ? 'bg-accent/15 text-accent'
                : 'text-text-muted hover:text-text-secondary'
            )}
          >
            All ({relationships.length})
          </button>
          {TIERS.filter((t) => countsByTier[t] > 0).map((tier) => (
            <button
              key={tier}
              onClick={() => setFilterTier(filterTier === tier ? null : tier)}
              className={cn(
                'rounded px-2 py-0.5 text-xs transition-colors',
                filterTier === tier
                  ? 'bg-accent/15 text-accent'
                  : 'text-text-muted hover:text-text-secondary'
              )}
            >
              <ConfidenceBadge tier={tier} />
              <span className="ml-1.5">{countsByTier[tier]}</span>
            </button>
          ))}
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {isLoading ? (
          <p className="text-sm text-text-secondary">Loading…</p>
        ) : filtered.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
            <p className="text-text-secondary text-sm">
              {relationships.length > 0
                ? 'No relationships match the selected filter'
                : 'No relationships yet'}
            </p>
            {relationships.length === 0 && (
              <p className="text-text-muted text-xs max-w-sm">
                Run inference to detect joins using structural, lexical, and statistical signals.
                Or add them manually / ask AI if you know what you're looking for.
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map((rel) => (
              <RelationshipCard key={rel.id} relationship={rel} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}


