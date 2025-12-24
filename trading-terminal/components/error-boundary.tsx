/**
 * Error Boundary Component
 * 
 * Catches JavaScript errors anywhere in the child component tree and
 * displays a fallback UI instead of crashing the whole page.
 * 
 * Usage:
 * ```tsx
 * <ErrorBoundary fallback={<ErrorFallback />}>
 *   <YourComponent />
 * </ErrorBoundary>
 * ```
 * 
 * @module components/error-boundary
 */

'use client'

import React, { Component, ErrorInfo, ReactNode } from 'react'
import { Card, CardContent, Button } from '@/components/ui'
import { AlertTriangle, RefreshCw, Home } from 'lucide-react'
import Link from 'next/link'

// ============================================================================
// Types
// ============================================================================

interface ErrorBoundaryProps {
  /** Content to render when there's no error */
  children: ReactNode
  /** Custom fallback UI (optional - uses default if not provided) */
  fallback?: ReactNode
  /** Callback when an error is caught */
  onError?: (error: Error, errorInfo: ErrorInfo) => void
  /** Optional custom reset function */
  onReset?: () => void
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
}

// ============================================================================
// Default Error Fallback
// ============================================================================

interface ErrorFallbackProps {
  error: Error | null
  errorInfo: ErrorInfo | null
  onRetry: () => void
}

/**
 * Default error fallback UI
 */
function DefaultErrorFallback({ error, onRetry }: ErrorFallbackProps) {
  return (
    <Card className="my-8 mx-4 border-red-500/50 bg-red-500/5">
      <CardContent className="pt-6">
        <div className="text-center">
          <div className="h-16 w-16 rounded-full bg-red-500/10 mx-auto flex items-center justify-center mb-4">
            <AlertTriangle className="h-8 w-8 text-red-500" />
          </div>
          
          <h2 className="text-xl font-semibold mb-2">Something went wrong</h2>
          
          <p className="text-muted-foreground mb-4 max-w-md mx-auto">
            An unexpected error occurred while rendering this section.
          </p>
          
          {error && (
            <details className="mb-6 text-left max-w-lg mx-auto">
              <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">
                View error details
              </summary>
              <pre className="mt-2 p-4 bg-muted rounded-lg text-xs overflow-auto max-h-40">
                <code>{error.message}</code>
                {error.stack && (
                  <>
                    {'\n\n'}
                    <code className="text-muted-foreground">{error.stack}</code>
                  </>
                )}
              </pre>
            </details>
          )}
          
          <div className="flex items-center justify-center gap-3">
            <Button onClick={onRetry} variant="default" className="gap-2">
              <RefreshCw className="h-4 w-4" />
              Try Again
            </Button>
            
            <Link href="/">
              <Button variant="outline" className="gap-2">
                <Home className="h-4 w-4" />
                Go Home
              </Button>
            </Link>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ============================================================================
// Error Boundary Class Component
// ============================================================================

/**
 * Error Boundary component using React's error boundary pattern
 * 
 * Note: Error boundaries must be class components as React doesn't
 * support hooks for error boundaries yet.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    }
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    // Update state so next render shows fallback UI
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Log error to console in development
    console.error('ErrorBoundary caught an error:', error, errorInfo)
    
    // Store error info for display
    this.setState({ errorInfo })
    
    // Call optional error callback
    this.props.onError?.(error, errorInfo)
  }

  handleReset = (): void => {
    // Call custom reset if provided
    this.props.onReset?.()
    
    // Clear error state
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    })
  }

  render(): ReactNode {
    const { hasError, error, errorInfo } = this.state
    const { children, fallback } = this.props

    if (hasError) {
      // Render custom fallback or default
      if (fallback) {
        return fallback
      }

      return (
        <DefaultErrorFallback
          error={error}
          errorInfo={errorInfo}
          onRetry={this.handleReset}
        />
      )
    }

    return children
  }
}

// ============================================================================
// Page-Level Error Boundary Wrapper
// ============================================================================

interface PageErrorBoundaryProps {
  children: ReactNode
  /** Page name for error logging */
  pageName?: string
}

/**
 * Convenience wrapper for page-level error boundaries
 * 
 * Usage:
 * ```tsx
 * export default function MyPage() {
 *   return (
 *     <PageErrorBoundary pageName="Portfolio">
 *       <PortfolioContent />
 *     </PageErrorBoundary>
 *   )
 * }
 * ```
 */
export function PageErrorBoundary({ children, pageName }: PageErrorBoundaryProps) {
  const handleError = (error: Error, errorInfo: ErrorInfo) => {
    // In production, you would send this to an error tracking service
    console.error(`[${pageName || 'Page'}] Error:`, error)
    console.error('Component stack:', errorInfo.componentStack)
  }

  return (
    <ErrorBoundary onError={handleError}>
      {children}
    </ErrorBoundary>
  )
}

// ============================================================================
// Section-Level Error Boundary
// ============================================================================

interface SectionErrorBoundaryProps {
  children: ReactNode
  /** Section name for context */
  sectionName?: string
  /** Compact fallback for smaller sections */
  compact?: boolean
}

/**
 * Compact error fallback for sections
 */
function CompactErrorFallback({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="p-4 rounded-lg border border-red-500/30 bg-red-500/5 text-center">
      <div className="flex items-center justify-center gap-2 text-red-500 mb-2">
        <AlertTriangle className="h-4 w-4" />
        <span className="text-sm font-medium">Failed to load</span>
      </div>
      <Button onClick={onRetry} variant="ghost" size="sm" className="text-xs">
        <RefreshCw className="h-3 w-3 mr-1" />
        Retry
      </Button>
    </div>
  )
}

/**
 * Error boundary for individual page sections
 * 
 * Usage:
 * ```tsx
 * <SectionErrorBoundary sectionName="Holdings" compact>
 *   <HoldingsList />
 * </SectionErrorBoundary>
 * ```
 */
export function SectionErrorBoundary({ 
  children, 
  sectionName,
  compact = false 
}: SectionErrorBoundaryProps) {
  const [key, setKey] = React.useState(0)

  const handleReset = () => {
    setKey(prev => prev + 1)
  }

  return (
    <ErrorBoundary
      key={key}
      onReset={handleReset}
      onError={(error) => {
        console.error(`[Section: ${sectionName || 'Unknown'}] Error:`, error)
      }}
      fallback={
        compact 
          ? <CompactErrorFallback onRetry={handleReset} />
          : undefined
      }
    >
      {children}
    </ErrorBoundary>
  )
}

export default ErrorBoundary
