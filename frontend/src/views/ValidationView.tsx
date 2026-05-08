import React, { useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { getValidationQueue, recordDecision } from '@/lib/api'
import { RelationshipCard } from '@/components/inference/RelationshipCard'
import { Button } from '@/components/common/Button'
import { useValidationStore } from '@/stores/validationStore'
import type { ValidationStatus } from '@/types'
import { cn } from '@/lib/utils'

export function ValidationView() {
  const { projectId } = useParams<{ projectId: string }>()
  const queryClient = useQueryClient()
  const { queue, progress, currentIndex, setQueue, recordLocalDecision, advance } =
    useValidationStore()

  const { isLoading, isError, refetch } = useQuery({
    queryKey: ['validation-queue', projectId],
    queryFn: async () => {
      const result = await getValidationQueue(projectId!)
      setQueue(result.batch, result.progress)
      return result
    },
    enabled: !!projectId,
    retry: false,
  })

  const decideMutation = useMutation({
    mutationFn: ({
      relationshipId,
      status,
    }: {
      relationshipId: string
      status: ValidationStatus
    }) => recordDecision(projectId!, { relationship_id: relationshipId, status }),
    onSuccess: (decision) => {
      recordLocalDecision(decision)
      advance()
      queryClient.invalidateQueries({ queryKey: ['memory', projectId] })
    },
    onError: () => toast.error('Failed to save decision'),
  })

  const current = queue[currentIndex] ?? null
  const isComplete = queue.length > 0 && currentIndex >= queue.length

  const completedPercent = progress
    ? Math.round(((progress.confirmed + progress.rejected) / (progress.total || 1)) * 100)
    : 0

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-surface-border px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-base font-semibold text-text-primary">Validation</h1>
            <p className="text-sm text-text-secondary">
              Review inferred relationships and confirm or reject them
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => refetch()}>
            Refresh Queue
          </Button>
        </div>

        {/* Progress bar */}
        {progress && (
          <div className="mt-3">
            <div className="flex items-center justify-between text-xs text-text-muted mb-1">
              <span>
                {progress.confirmed} confirmed · {progress.rejected} rejected ·{' '}
                {progress.pending} pending
              </span>
              <span>{completedPercent}%</span>
            </div>
            <div className="h-1 overflow-hidden rounded-full bg-surface-overlay">
              <div
                className="h-full rounded-full bg-status-confirmed transition-all"
                style={{ width: `${completedPercent}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Validation content */}
      <div className="flex-1 overflow-y-auto p-6">
        {isLoading ? (
          <p className="text-sm text-text-secondary">Loading queue…</p>
        ) : isError || queue.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
            <p className="text-text-secondary text-sm">No relationships to validate</p>
            <p className="text-text-muted text-xs max-w-xs">
              Run inference first to generate relationships for review.
            </p>
          </div>
        ) : isComplete ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
            <p className="text-status-confirmed text-sm font-medium">Batch complete!</p>
            <p className="text-text-muted text-xs">
              All {queue.length} relationships in this batch have been reviewed.
            </p>
            <Button variant="secondary" size="sm" onClick={() => refetch()}>
              Load Next Batch
            </Button>
          </div>
        ) : (
          <div className="mx-auto max-w-2xl space-y-6">
            {/* Current item — large */}
            <div>
              <div className="mb-2 flex items-center justify-between">
                <p className="text-xs text-text-muted">
                  {currentIndex + 1} / {queue.length}
                </p>
              </div>
              {current && (
                <RelationshipCard
                  relationship={current}
                  validationStatus="pending"
                  onConfirm={() =>
                    decideMutation.mutate({
                      relationshipId: current.id,
                      status: 'confirmed',
                    })
                  }
                  onReject={() =>
                    decideMutation.mutate({
                      relationshipId: current.id,
                      status: 'rejected',
                    })
                  }
                  onDefer={() =>
                    decideMutation.mutate({
                      relationshipId: current.id,
                      status: 'deferred',
                    })
                  }
                />
              )}
            </div>

            {/* Upcoming queue preview */}
            {queue.slice(currentIndex + 1, currentIndex + 4).length > 0 && (
              <div>
                <p className="mb-2 text-xs font-medium text-text-muted uppercase tracking-widest">
                  Up next
                </p>
                <div className="space-y-2 opacity-50">
                  {queue.slice(currentIndex + 1, currentIndex + 4).map((rel) => (
                    <RelationshipCard key={rel.id} relationship={rel} compact />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
