import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { Position } from '@/lib/api'
import { cn, formatCurrency, formatPercent, formatNumber, getPnLColorClass, getPnLBgClass } from '@/lib/utils'

interface PositionCardProps {
  position: Position
}

/**
 * Card component displaying a single trading position
 */
export function PositionCard({ position }: PositionCardProps) {
  const {
    symbol,
    direction,
    quantity,
    avg_price,
    current_price,
    unrealized_pnl,
    unrealized_pnl_pct,
    dca_attempts,
  } = position

  const isProfit = unrealized_pnl >= 0
  const TrendIcon = unrealized_pnl > 0 ? TrendingUp : unrealized_pnl < 0 ? TrendingDown : Minus

  return (
    <div className={cn(
      'position-card',
      getPnLBgClass(unrealized_pnl)
    )}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold">{symbol}</span>
          <span className={cn(
            'px-2 py-0.5 rounded text-xs font-medium',
            direction === 'long' ? 'bg-profit/20 text-profit' : 'bg-loss/20 text-loss'
          )}>
            {direction.toUpperCase()}
          </span>
        </div>
        <TrendIcon className={cn('w-5 h-5', getPnLColorClass(unrealized_pnl))} />
      </div>

      {/* P&L Display */}
      <div className="mb-4">
        <div className={cn('text-2xl font-bold', getPnLColorClass(unrealized_pnl))}>
          {formatCurrency(unrealized_pnl)}
        </div>
        <div className={cn('text-sm', getPnLColorClass(unrealized_pnl))}>
          {formatPercent(unrealized_pnl_pct)}
        </div>
      </div>

      {/* Position Details */}
      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Quantity</span>
          <span className="font-medium">{formatNumber(quantity, 0)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Avg Price</span>
          <span className="font-medium">{formatCurrency(avg_price)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Current</span>
          <span className={cn('font-medium', getPnLColorClass(current_price - avg_price))}>
            {formatCurrency(current_price)}
          </span>
        </div>
        {dca_attempts !== undefined && dca_attempts > 0 && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">DCA Attempts</span>
            <span className="font-medium text-amber-500">{dca_attempts}</span>
          </div>
        )}
      </div>

      {/* Position Value */}
      <div className="mt-4 pt-3 border-t">
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">Position Value</span>
          <span className="font-medium">
            {formatCurrency(quantity * current_price)}
          </span>
        </div>
      </div>
    </div>
  )
}
