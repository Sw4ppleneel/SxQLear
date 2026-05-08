import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
import type { ConfidenceTier, ValidationStatus } from '@/types'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export const CONFIDENCE_CONFIG: Record<
  ConfidenceTier,
  { label: string; color: string; bgColor: string; borderColor: string }
> = {
  certain: {
    label: 'Certain',
    color: 'text-confidence-certain',
    bgColor: 'bg-confidence-certain/10',
    borderColor: 'border-confidence-certain/30',
  },
  high: {
    label: 'High',
    color: 'text-confidence-high',
    bgColor: 'bg-confidence-high/10',
    borderColor: 'border-confidence-high/30',
  },
  medium: {
    label: 'Medium',
    color: 'text-confidence-medium',
    bgColor: 'bg-confidence-medium/10',
    borderColor: 'border-confidence-medium/30',
  },
  low: {
    label: 'Low',
    color: 'text-confidence-low',
    bgColor: 'bg-confidence-low/10',
    borderColor: 'border-confidence-low/30',
  },
  speculative: {
    label: 'Speculative',
    color: 'text-confidence-speculative',
    bgColor: 'bg-confidence-speculative/10',
    borderColor: 'border-confidence-speculative/30',
  },
}

export const STATUS_CONFIG: Record<ValidationStatus, { label: string; color: string }> = {
  pending: { label: 'Pending', color: 'text-text-secondary' },
  confirmed: { label: 'Confirmed', color: 'text-status-confirmed' },
  rejected: { label: 'Rejected', color: 'text-status-rejected' },
  deferred: { label: 'Deferred', color: 'text-status-deferred' },
}

export function formatScore(score: number): string {
  return `${(score * 100).toFixed(0)}%`
}

export function formatRowCount(count?: number): string {
  if (!count) return '—'
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}k`
  return count.toLocaleString()
}

export function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
