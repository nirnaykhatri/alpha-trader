/**
 * Empty State Component
 * 
 * Reusable component for displaying empty states with icon, title, description, and actions.
 * 
 * @module components/empty-state
 */

import React, { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { RefreshCw, AlertCircle, type LucideIcon } from 'lucide-react'

export interface EmptyStateProps {
  /** Title text */
  title: string
  /** Description text */
  description: string
  /** Lucide icon component to display */
  icon?: LucideIcon
  /** Custom icon element (for more control) */
  iconElement?: ReactNode
  /** Icon background color class */
  iconBgColor?: string
  /** Icon color class */
  iconColor?: string
  /** Action buttons or content */
  action?: ReactNode
  /** Whether to wrap in a Card component */
  withCard?: boolean
  /** Custom className for the container */
  className?: string
}

/**
 * Generic empty state component for displaying when no data is available.
 * 
 * @example
 * // Simple usage
 * <EmptyState
 *   title="No bots found"
 *   description="Create your first trading bot to get started."
 *   icon={Bot}
 *   action={<Button>Create Bot</Button>}
 * />
 * 
 * @example
 * // With card wrapper and multiple actions
 * <EmptyState
 *   title="No Data Available"
 *   description="Unable to connect to the API."
 *   icon={AlertCircle}
 *   withCard
 *   action={
 *     <div className="flex gap-3">
 *       <Button variant="outline" onClick={retry}>Retry</Button>
 *       <Button onClick={useDemoMode}>Use Demo</Button>
 *     </div>
 *   }
 * />
 */
export function EmptyState({
  title,
  description,
  icon: Icon,
  iconElement,
  iconBgColor = 'bg-muted',
  iconColor = 'text-muted-foreground',
  action,
  withCard = false,
  className,
}: EmptyStateProps) {
  const content = (
    <div className={cn('flex flex-col items-center justify-center py-12 text-center', className)}>
      {(Icon || iconElement) && (
        <div className={cn('h-16 w-16 rounded-full flex items-center justify-center mb-4', iconBgColor)}>
          {iconElement || (Icon && <Icon className={cn('h-8 w-8', iconColor)} />)}
        </div>
      )}
      <h3 className="text-lg font-medium">{title}</h3>
      <p className="text-sm text-muted-foreground mt-1 max-w-md">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  )

  if (withCard) {
    return (
      <Card className="border-muted">
        <CardContent>{content}</CardContent>
      </Card>
    )
  }

  return content
}

/**
 * Pre-configured empty state for API connection errors
 */
export interface ApiErrorEmptyStateProps {
  /** Error message to display */
  message?: string
  /** Retry callback */
  onRetry?: () => void
  /** Demo mode callback */
  onUseDemoMode?: () => void
  /** Custom icon */
  icon?: LucideIcon
  /** Whether to show in a Card */
  withCard?: boolean
}

export function ApiErrorEmptyState({
  message = 'Unable to connect to the trading API. Check your backend connection or try demo mode.',
  onRetry,
  onUseDemoMode,
  icon: Icon = AlertCircle,
  withCard = true,
}: ApiErrorEmptyStateProps) {
  return (
    <EmptyState
      title="Connection Error"
      description={message}
      icon={Icon}
      iconBgColor="bg-destructive/10"
      iconColor="text-destructive"
      withCard={withCard}
      action={
        (onRetry || onUseDemoMode) && (
          <div className="flex gap-3">
            {onRetry && (
              <Button variant="outline" onClick={onRetry}>
                <RefreshCw className="h-4 w-4 mr-2" />
                Retry Connection
              </Button>
            )}
            {onUseDemoMode && (
              <Button onClick={onUseDemoMode}>
                Use Demo Data
              </Button>
            )}
          </div>
        )
      }
    />
  )
}
