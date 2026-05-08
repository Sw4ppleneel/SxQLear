import React from 'react'
import { cn } from '@/lib/utils'
import type { ConfidenceTier, ValidationStatus } from '@/types'
import { CONFIDENCE_CONFIG, STATUS_CONFIG, formatScore } from '@/lib/utils'

interface ConfidenceBadgeProps {
  tier: ConfidenceTier
  score?: number
  className?: string
}

export function ConfidenceBadge({ tier, score, className }: ConfidenceBadgeProps) {
  const config = CONFIDENCE_CONFIG[tier]
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs font-medium border',
        config.color,
        config.bgColor,
        config.borderColor,
        className
      )}
    >
      <span
        className={cn('h-1.5 w-1.5 rounded-full', {
          'bg-confidence-certain': tier === 'certain',
          'bg-confidence-high': tier === 'high',
          'bg-confidence-medium': tier === 'medium',
          'bg-confidence-low': tier === 'low',
          'bg-confidence-speculative': tier === 'speculative',
        })}
      />
      {config.label}
      {score !== undefined && <span className="opacity-60">{formatScore(score)}</span>}
    </span>
  )
}

interface StatusBadgeProps {
  status: ValidationStatus
  className?: string
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status]
  return (
    <span
      className={cn(
        'inline-flex items-center rounded px-2 py-0.5 text-xs font-medium',
        'bg-surface-overlay border border-surface-border',
        config.color,
        className
      )}
    >
      {config.label}
    </span>
  )
}
