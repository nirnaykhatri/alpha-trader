/**
 * Theme Selector Component
 * 
 * Dropdown menu for selecting application theme mode.
 * Supports Light, Dark, and System (auto-detect) modes.
 * 
 * @module components/trading/theme-selector
 */

'use client'

import React from 'react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { useTheme } from '@/lib/contexts'
import { Sun, Moon, Monitor, Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ThemeMode } from '@/lib/contexts'

interface ThemeSelectorProps {
  /** Additional CSS classes */
  className?: string
  /** Show text label next to icon */
  showLabel?: boolean
}

const THEME_OPTIONS: { value: ThemeMode; label: string; icon: React.ReactNode }[] = [
  { value: 'light', label: 'Light', icon: <Sun className="h-4 w-4" /> },
  { value: 'dark', label: 'Dark', icon: <Moon className="h-4 w-4" /> },
  { value: 'system', label: 'System', icon: <Monitor className="h-4 w-4" /> },
]

/**
 * Theme Selector Dropdown
 * 
 * Provides a dropdown menu for selecting the application theme.
 * Shows current theme icon and allows switching between Light/Dark/System.
 * 
 * @example
 * ```tsx
 * <ThemeSelector showLabel />
 * ```
 */
export function ThemeSelector({
  className,
  showLabel = false,
}: ThemeSelectorProps): JSX.Element {
  const { theme, setTheme, resolvedTheme } = useTheme()

  // Get the icon for the current theme
  const currentOption = THEME_OPTIONS.find(opt => opt.value === theme)
  const CurrentIcon = resolvedTheme === 'dark' ? Moon : Sun

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className={cn('h-9 w-9', className)}>
          <CurrentIcon className="h-4 w-4" />
          {showLabel && (
            <span className="ml-2 text-sm">{currentOption?.label}</span>
          )}
          <span className="sr-only">Toggle theme</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {THEME_OPTIONS.map((option) => (
          <DropdownMenuItem
            key={option.value}
            onClick={() => setTheme(option.value)}
            className="flex items-center justify-between gap-2"
          >
            <div className="flex items-center gap-2">
              {option.icon}
              <span>{option.label}</span>
            </div>
            {theme === option.value && (
              <Check className="h-4 w-4 text-primary" />
            )}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export default ThemeSelector
