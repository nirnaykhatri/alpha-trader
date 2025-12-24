/**
 * Account Mode Toggle Component
 * 
 * Toggle switch for switching between Demo and Live trading modes.
 * Displays a prominent indicator of the current mode.
 * 
 * @module components/trading/account-mode-toggle
 */

'use client'

import React from 'react'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { useAppSettings } from '@/lib/contexts'
import { cn } from '@/lib/utils'

interface AccountModeToggleProps {
  /** Additional CSS classes */
  className?: string
  /** Show mode label */
  showLabel?: boolean
  /** Compact mode for smaller spaces */
  compact?: boolean
  /** Size variant */
  size?: 'sm' | 'md' | 'lg'
}

/**
 * Account Mode Toggle
 * 
 * Provides a visual toggle for switching between Demo and Live trading modes.
 * Demo mode is highlighted in blue, Live mode in green.
 * 
 * @example
 * ```tsx
 * <AccountModeToggle showLabel />
 * ```
 */
export function AccountModeToggle({
  className,
  showLabel = true,
  compact = false,
  size = 'md',
}: AccountModeToggleProps): JSX.Element {
  const { accountMode, toggleAccountMode, isDemo, isLive } = useAppSettings()

  const sizeClasses = {
    sm: 'text-xs gap-1',
    md: 'text-sm gap-2',
    lg: 'text-base gap-3',
  }

  return (
    <div className={cn('flex items-center', sizeClasses[size], className)}>
      {showLabel && !compact && (
        <span className="text-sm text-muted-foreground">Demo</span>
      )}
      
      <div className="relative">
        <Switch
          checked={isLive}
          onCheckedChange={toggleAccountMode}
          className={cn(
            'data-[state=checked]:bg-green-600 data-[state=unchecked]:bg-blue-600',
          )}
        />
      </div>
      
      {showLabel && !compact && (
        <span className="text-sm text-muted-foreground">Live</span>
      )}
      
      {/* Mode Badge */}
      <Badge
        variant="outline"
        className={cn(
          'ml-1 font-semibold',
          isDemo && 'bg-blue-500/20 text-blue-400 border-blue-500/30',
          isLive && 'bg-green-500/20 text-green-400 border-green-500/30',
        )}
      >
        {isDemo ? 'Demo' : 'Live'}
      </Badge>
    </div>
  )
}

export default AccountModeToggle
