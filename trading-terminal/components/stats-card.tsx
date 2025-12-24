import { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import type { LucideIcon } from 'lucide-react'

/**
 * Trend colors for styling based on value direction
 */
const TREND_COLORS = {
  up: 'text-emerald-500',
  down: 'text-red-500',
  neutral: 'text-muted-foreground',
} as const

export interface StatsCardProps {
  /** Title/label for the stat */
  title: string
  /** Primary value to display */
  value: string
  /** Secondary value or additional info (e.g., "5 total") */
  subValue?: string
  /** Lucide icon component to display */
  icon?: LucideIcon
  /** Optional icon as React element (for backward compatibility) */
  iconElement?: ReactNode
  /** Trend direction for coloring */
  trend?: 'up' | 'down' | 'neutral'
  /** Visual variant */
  variant?: 'default' | 'compact'
  /** Custom icon background color class */
  iconBgColor?: string
  /** Custom icon color class */
  iconColor?: string
}

/**
 * Reusable stats card component for displaying metrics with optional icons and trends.
 * 
 * @example
 * // With Lucide icon component
 * <StatsCard
 *   title="Active Bots"
 *   value="5"
 *   subValue="10 total"
 *   icon={Activity}
 * />
 * 
 * @example
 * // With trend indicator
 * <StatsCard
 *   title="Total PnL"
 *   value="$1,234.56"
 *   icon={TrendingUp}
 *   trend="up"
 * />
 * 
 * @example
 * // Compact variant (no Card wrapper)
 * <StatsCard
 *   title="Win Rate"
 *   value="65%"
 *   iconElement={<TrendingUp className="h-4 w-4" />}
 *   variant="compact"
 * />
 */
export function StatsCard({ 
  title, 
  value, 
  subValue,
  icon: Icon, 
  iconElement,
  trend,
  variant = 'default',
  iconBgColor = 'bg-primary/10',
  iconColor = 'text-primary',
}: StatsCardProps) {
  const valueColorClass = trend ? TREND_COLORS[trend] : ''

  // Compact variant - simple div structure (backward compatible)
  if (variant === 'compact') {
    return (
      <div className="stat-card">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-muted-foreground">{title}</span>
          {iconElement && (
            <span className="text-muted-foreground">{iconElement}</span>
          )}
          {Icon && !iconElement && (
            <Icon className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
        <div className={cn('text-2xl font-bold', valueColorClass)}>
          {value}
        </div>
        {subValue && (
          <p className="text-xs text-muted-foreground mt-1">{subValue}</p>
        )}
      </div>
    )
  }

  // Default variant - Card with icon badge
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm text-muted-foreground">{title}</p>
            <p className={cn('text-2xl font-bold mt-1', valueColorClass)}>
              {value}
            </p>
            {subValue && (
              <p className="text-xs text-muted-foreground mt-1">{subValue}</p>
            )}
          </div>
          {(Icon || iconElement) && (
            <div className={cn('h-10 w-10 rounded-lg flex items-center justify-center', iconBgColor)}>
              {iconElement || (Icon && <Icon className={cn('h-5 w-5', iconColor)} />)}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
