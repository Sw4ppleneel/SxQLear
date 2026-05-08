import { create } from 'zustand'
import type { ValidationDecision, ValidationQueueProgress, InferredRelationship } from '@/types'

interface ValidationState {
  queue: InferredRelationship[]
  progress: ValidationQueueProgress | null
  decisions: Record<string, ValidationDecision> // keyed by relationship_id
  currentIndex: number

  setQueue: (queue: InferredRelationship[], progress: ValidationQueueProgress) => void
  recordLocalDecision: (decision: ValidationDecision) => void
  advance: () => void
  reset: () => void
}

export const useValidationStore = create<ValidationState>((set) => ({
  queue: [],
  progress: null,
  decisions: {},
  currentIndex: 0,

  setQueue: (queue, progress) => set({ queue, progress, currentIndex: 0 }),

  recordLocalDecision: (decision) =>
    set((state) => ({
      decisions: {
        ...state.decisions,
        [decision.relationship_id]: decision,
      },
    })),

  advance: () =>
    set((state) => ({
      currentIndex: Math.min(state.currentIndex + 1, state.queue.length - 1),
    })),

  reset: () => set({ queue: [], progress: null, decisions: {}, currentIndex: 0 }),
}))
