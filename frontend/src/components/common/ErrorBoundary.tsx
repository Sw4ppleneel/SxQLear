import { Component, type ErrorInfo, type ReactNode } from 'react'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  error: Error | null
}

/**
 * A single crashing view (e.g. a field that doesn't exist on the API
 * response) should never blank the whole app — it did before this existed.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled error in view:', error, info.componentStack)
  }

  private reset = () => this.setState({ error: null })

  render() {
    if (this.state.error) {
      return (
        <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
          <p className="text-sm font-semibold text-text-primary">Something went wrong</p>
          <p className="max-w-md text-xs text-text-secondary">{this.state.error.message}</p>
          <button
            onClick={this.reset}
            className="mt-2 rounded border border-surface-border bg-surface-elevated px-3 py-1.5 text-xs text-text-primary hover:bg-surface-elevated/70"
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
