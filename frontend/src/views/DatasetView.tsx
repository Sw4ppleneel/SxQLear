import React, { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Code, Plus, FileText } from 'lucide-react'
import {
  getLatestSnapshot,
  getRelationships,
  buildDatasetPlan,
  listDatasetPlans,
  getDatasetPlan,
  generateSQL,
} from '@/lib/api'
import { Button } from '@/components/common/Button'
import { RelationshipCard } from '@/components/inference/RelationshipCard'
import type { DatasetPlan } from '@/types'
import { cn } from '@/lib/utils'

export function DatasetView() {
  const { projectId } = useParams<{ projectId: string }>()
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null)
  const [showBuilder, setShowBuilder] = useState(false)
  const [sql, setSql] = useState<string | null>(null)

  // Build form state
  const [form, setForm] = useState({
    name: '',
    description: '',
    base_table: '',
    grain_description: '',
    include_tables: [] as string[],
  })

  const { data: snapshot } = useQuery({
    queryKey: ['snapshot', projectId],
    queryFn: () => getLatestSnapshot(projectId!),
    enabled: !!projectId,
    retry: false,
  })

  const { data: relationships = [] } = useQuery({
    queryKey: ['relationships', projectId],
    queryFn: () => getRelationships(projectId!),
    enabled: !!projectId,
  })

  const { data: plans = [], refetch: refetchPlans } = useQuery({
    queryKey: ['dataset-plans', projectId],
    queryFn: () => listDatasetPlans(projectId!),
    enabled: !!projectId,
  })

  const { data: activePlan } = useQuery({
    queryKey: ['dataset-plan', projectId, selectedPlanId],
    queryFn: () => getDatasetPlan(projectId!, selectedPlanId!),
    enabled: !!projectId && !!selectedPlanId,
  })

  const buildMutation = useMutation({
    mutationFn: () => buildDatasetPlan(projectId!, form),
    onSuccess: (plan) => {
      refetchPlans()
      setSelectedPlanId(plan.id)
      setShowBuilder(false)
      toast.success('Dataset plan created')
    },
    onError: () => toast.error('Failed to build plan'),
  })

  const sqlMutation = useMutation({
    mutationFn: () => generateSQL(projectId!, selectedPlanId!),
    onSuccess: (result) => setSql(result.sql),
    onError: () => toast.error('Failed to generate SQL'),
  })

  const confirmedRelationships = relationships.filter(
    (r) => r.confidence === 'certain' || r.confidence === 'high'
  )

  const tables = snapshot?.tables ?? []

  function toggleIncludeTable(name: string) {
    setForm((f) => ({
      ...f,
      include_tables: f.include_tables.includes(name)
        ? f.include_tables.filter((t) => t !== name)
        : [...f.include_tables, name],
    }))
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-surface-border px-6 py-4">
        <div>
          <h1 className="text-base font-semibold text-text-primary">Datasets</h1>
          <p className="text-sm text-text-secondary">
            Build join plans from confirmed relationships
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={() => setShowBuilder(true)}>
          <Plus className="h-3.5 w-3.5" />
          New Plan
        </Button>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Plan list */}
        <div className="w-64 flex-shrink-0 overflow-y-auto border-r border-surface-border bg-surface-elevated">
          <div className="border-b border-surface-border px-3 py-2">
            <p className="text-xs font-medium text-text-secondary">Plans ({plans.length})</p>
          </div>
          {plans.length === 0 ? (
            <p className="p-4 text-xs text-text-muted">No plans yet</p>
          ) : (
            plans.map((plan) => (
              <button
                key={plan.id}
                onClick={() => { setSelectedPlanId(plan.id); setSql(null) }}
                className={cn(
                  'w-full px-3 py-2.5 text-left text-xs transition-colors border-b border-surface-border/50',
                  selectedPlanId === plan.id
                    ? 'bg-accent/10 text-accent'
                    : 'text-text-secondary hover:bg-surface-hover hover:text-text-primary'
                )}
              >
                <p className="font-medium truncate">{plan.name}</p>
                <p className="text-text-muted capitalize mt-0.5">{plan.status}</p>
              </button>
            ))
          )}
        </div>

        {/* Plan detail / builder */}
        <div className="flex-1 overflow-y-auto p-6">
          {showBuilder ? (
            <div className="mx-auto max-w-xl space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-text-primary">New Dataset Plan</h2>
                <button
                  onClick={() => setShowBuilder(false)}
                  className="text-xs text-text-muted hover:text-text-secondary"
                >
                  Cancel
                </button>
              </div>

              <Field label="Plan name">
                <input
                  className={inputClass}
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Customer analysis flat table"
                />
              </Field>
              <Field label="Description">
                <input
                  className={inputClass}
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="What is this dataset for?"
                />
              </Field>
              <Field label="Grain (optional)">
                <input
                  className={inputClass}
                  value={form.grain_description}
                  onChange={(e) => setForm({ ...form, grain_description: e.target.value })}
                  placeholder="One row per customer order"
                />
              </Field>
              <Field label="Base table">
                <select
                  className={inputClass}
                  value={form.base_table}
                  onChange={(e) => setForm({ ...form, base_table: e.target.value })}
                >
                  <option value="">Select base table…</option>
                  {tables.map((t) => (
                    <option key={t.name} value={t.name}>{t.name}</option>
                  ))}
                </select>
              </Field>
              <Field label="Include tables">
                <div className="grid grid-cols-2 gap-1 mt-1">
                  {tables
                    .filter((t) => t.name !== form.base_table)
                    .map((t) => (
                      <label key={t.name} className="flex items-center gap-1.5 text-xs text-text-secondary cursor-pointer">
                        <input
                          type="checkbox"
                          checked={form.include_tables.includes(t.name)}
                          onChange={() => toggleIncludeTable(t.name)}
                          className="rounded border-surface-border accent-accent"
                        />
                        <span className="font-mono truncate">{t.name}</span>
                      </label>
                    ))}
                </div>
              </Field>
              <Button
                variant="primary"
                size="sm"
                onClick={() => buildMutation.mutate()}
                loading={buildMutation.isPending}
                disabled={!form.name || !form.base_table}
              >
                Build Plan
              </Button>
            </div>
          ) : activePlan ? (
            <PlanDetail plan={activePlan} onGenerateSQL={() => sqlMutation.mutate()} sql={sql} generating={sqlMutation.isPending} />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
              <FileText className="h-8 w-8 text-text-muted" />
              <p className="text-text-secondary text-sm">Select a plan or create a new one</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function PlanDetail({
  plan,
  onGenerateSQL,
  sql,
  generating,
}: {
  plan: DatasetPlan
  onGenerateSQL: () => void
  sql: string | null
  generating: boolean
}) {
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">{plan.name}</h2>
          {plan.description && (
            <p className="text-xs text-text-secondary mt-0.5">{plan.description}</p>
          )}
          {plan.grain_description && (
            <p className="text-xs text-text-muted mt-1">Grain: {plan.grain_description}</p>
          )}
        </div>
        <Button
          variant="primary"
          size="sm"
          onClick={onGenerateSQL}
          loading={generating}
        >
          <Code className="h-3.5 w-3.5" />
          Generate SQL
        </Button>
      </div>

      {/* Joins */}
      {plan.joins.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-widest text-text-muted">
            Joins ({plan.joins.length})
          </h3>
          <div className="space-y-1.5">
            {plan.joins.map((join, i) => (
              <div key={i} className="rounded border border-surface-border bg-surface-elevated px-3 py-2 text-xs">
                <span className="font-mono text-accent/80 mr-2">{join.join_type}</span>
                <span className="font-mono text-text-primary">{join.right_table}</span>
                <span className="text-text-muted mx-1">ON</span>
                <span className="font-mono text-text-secondary">
                  {join.left_table}.{join.left_column} = {join.right_table}.{join.right_column}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Assumptions & warnings */}
      {plan.assumptions.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-widest text-text-muted">
            Assumptions
          </h3>
          <ul className="space-y-1">
            {plan.assumptions.map((a, i) => (
              <li key={i} className="text-xs text-text-secondary">• {a}</li>
            ))}
          </ul>
        </section>
      )}

      {plan.warnings.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-widest text-status-deferred">
            Warnings
          </h3>
          <ul className="space-y-1">
            {plan.warnings.map((w, i) => (
              <li key={i} className="text-xs text-status-deferred">⚠ {w}</li>
            ))}
          </ul>
        </section>
      )}

      {/* SQL Output */}
      {sql && (
        <section>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-widest text-text-muted">
            Generated SQL
          </h3>
          <pre className="overflow-x-auto rounded border border-surface-border bg-surface p-4 font-mono text-xs text-text-primary whitespace-pre">
            {sql}
          </pre>
        </section>
      )}
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
