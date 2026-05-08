import React from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getMemorySummary, getRelationships } from '@/lib/api'
import { RelationshipCard } from '@/components/inference/RelationshipCard'
import { ConfidenceBadge, StatusBadge } from '@/components/common/Badges'
import { formatDate, formatRowCount } from '@/lib/utils'

export function MemoryView() {
  const { projectId } = useParams<{ projectId: string }>()

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['memory', projectId],
    queryFn: () => getMemorySummary(projectId!),
    enabled: !!projectId,
  })

  const { data: relationships = [], isLoading: relsLoading } = useQuery({
    queryKey: ['relationships', projectId],
    queryFn: () => getRelationships(projectId!),
    enabled: !!projectId,
  })

  const confirmed = relationships.filter(
    (r) => summary?.validated_relationship_ids.includes(r.id)
  )

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-surface-border px-6 py-4">
        <h1 className="text-base font-semibold text-text-primary">Memory</h1>
        <p className="text-sm text-text-secondary">
          Analytical memory accumulated for this project
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-8">
        {/* Summary stats */}
        {summary && (
          <div className="grid grid-cols-4 gap-3">
            <StatCard label="Total Tables" value={summary.total_tables} />
            <StatCard label="Total Columns" value={summary.total_columns} />
            <StatCard label="Inferred Relationships" value={summary.relationship_count} />
            <StatCard label="Confirmed" value={summary.confirmed_count} />
          </div>
        )}

        {/* Confirmed relationships */}
        <section>
          <h2 className="mb-3 text-xs font-medium uppercase tracking-widest text-text-muted">
            Confirmed Relationships ({confirmed.length})
          </h2>
          {relsLoading ? (
            <p className="text-sm text-text-secondary">Loading…</p>
          ) : confirmed.length === 0 ? (
            <p className="text-sm text-text-muted">
              No confirmed relationships yet. Use the Validation view to confirm inferred joins.
            </p>
          ) : (
            <div className="space-y-2">
              {confirmed.map((rel) => (
                <RelationshipCard
                  key={rel.id}
                  relationship={rel}
                  validationStatus="confirmed"
                  compact
                />
              ))}
            </div>
          )}
        </section>

        {/* Annotations */}
        {summary?.annotations && summary.annotations.length > 0 && (
          <section>
            <h2 className="mb-3 text-xs font-medium uppercase tracking-widest text-text-muted">
              Annotations ({summary.annotations.length})
            </h2>
            <div className="space-y-2">
              {summary.annotations.map((ann) => (
                <div
                  key={ann.id}
                  className="rounded border border-surface-border bg-surface-elevated px-4 py-3"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-xs text-text-primary">
                      {ann.target_identifier}
                    </span>
                    <StatusBadge status="confirmed" />
                    <span className="text-2xs text-text-muted capitalize">
                      {ann.annotation_type}
                    </span>
                  </div>
                  <p className="text-xs text-text-secondary">{ann.text}</p>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-surface-border bg-surface-elevated px-4 py-3">
      <p className="text-2xs text-text-muted">{label}</p>
      <p className="text-xl font-semibold text-text-primary">{value.toLocaleString()}</p>
    </div>
  )
}
