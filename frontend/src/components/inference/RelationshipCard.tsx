import React, { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { InferredRelationship, SignalType } from '@/types'
import { ConfidenceBadge, StatusBadge } from '@/components/common/Badges'
import { Button } from '@/components/common/Button'
import { cn, formatScore } from '@/lib/utils'

const SIGNAL_LABELS: Record<SignalType, string> = {
  structural: 'Structural',
  lexical: 'Lexical',
  statistical: 'Statistical',
  semantic: 'Semantic',
  llm: 'LLM',
  manual: 'Manual',
}

interface RelationshipCardProps {
  relationship: InferredRelationship
  validationStatus?: string
  onConfirm?: () => void
  onReject?: () => void
  onDefer?: () => void
  compact?: boolean
  className?: string
}

export function RelationshipCard({
  relationship: rel,
  validationStatus = 'pending',
  onConfirm,
  onReject,
  onDefer,
  compact = false,
  className,
}: RelationshipCardProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      className={cn(
        'rounded border bg-surface-elevated transition-colors',
        validationStatus === 'confirmed' && 'border-status-confirmed/30',
        validationStatus === 'rejected' && 'border-status-rejected/30 opacity-60',
        validationStatus === 'pending' && 'border-surface-border hover:border-surface-hover',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-start gap-3 p-3">
        <div className="flex-1 min-w-0">
          {/* Join expression */}
          <div className="flex items-center gap-1.5 font-mono text-sm text-text-primary">
            <span className="text-accent">{rel.source_table}</span>
            <span className="text-text-muted">.</span>
            <span className="text-text-primary">{rel.source_column}</span>
            <span className="mx-1 text-text-muted">→</span>
            <span className="text-confidence-high">{rel.target_table}</span>
            <span className="text-text-muted">.</span>
            <span className="text-text-primary">{rel.target_column}</span>
          </div>
          <div className="mt-1 flex items-center gap-2">
            <ConfidenceBadge tier={rel.confidence} score={rel.composite_score} />
            <StatusBadge status={validationStatus as any} />
            <span className="text-2xs text-text-muted capitalize">{rel.relationship_type}</span>
          </div>
        </div>

        {/* Actions */}
        {validationStatus === 'pending' && (onConfirm || onReject) && (
          <div className="flex items-center gap-1.5 flex-shrink-0">
            {onConfirm && (
              <Button size="sm" variant="primary" onClick={onConfirm}>
                Confirm
              </Button>
            )}
            {onReject && (
              <Button size="sm" variant="destructive" onClick={onReject}>
                Reject
              </Button>
            )}
            {onDefer && (
              <Button size="sm" variant="ghost" onClick={onDefer}>
                Later
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Evidence toggle */}
      {!compact && rel.evidence.length > 0 && (
        <>
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex w-full items-center gap-1.5 border-t border-surface-border px-3 py-1.5 text-left text-2xs text-text-muted hover:text-text-secondary transition-colors"
          >
            {expanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
            {rel.evidence.length} signal{rel.evidence.length !== 1 ? 's' : ''}
          </button>

          {expanded && (
            <div className="border-t border-surface-border px-3 pb-3 pt-2 space-y-2">
              {rel.evidence.map((ev, i) => (
                <div key={i} className="text-xs">
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="font-medium text-text-secondary">
                      {SIGNAL_LABELS[ev.signal_type]}
                    </span>
                    <span className="font-mono text-text-muted">
                      {formatScore(ev.score)} (w={ev.weight.toFixed(2)})
                    </span>
                  </div>
                  <p className="text-text-muted leading-relaxed">{ev.reasoning}</p>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
