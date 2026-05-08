import React from 'react'
import { cn } from '@/lib/utils'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'destructive'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  disabled,
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded font-medium transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
        'disabled:opacity-40 disabled:cursor-not-allowed',
        {
          // Variants
          'bg-accent text-white hover:bg-accent-hover': variant === 'primary',
          'bg-surface-elevated border border-surface-border text-text-primary hover:bg-surface-hover':
            variant === 'secondary',
          'text-text-secondary hover:text-text-primary hover:bg-surface-hover': variant === 'ghost',
          'bg-confidence-speculative/10 border border-confidence-speculative/30 text-confidence-speculative hover:bg-confidence-speculative/20':
            variant === 'destructive',
          // Sizes
          'px-2.5 py-1 text-xs': size === 'sm',
          'px-3.5 py-1.5 text-sm': size === 'md',
          'px-5 py-2 text-base': size === 'lg',
        },
        className
      )}
      {...props}
    >
      {loading && (
        <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
          />
        </svg>
      )}
      {children}
    </button>
  )
}
