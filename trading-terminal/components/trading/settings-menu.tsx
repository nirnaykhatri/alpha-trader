/**
 * Settings Menu Component
 * 
 * Comprehensive settings dropdown combining:
 * - Demo/Live account toggle
 * - Theme selector (Light/Dark/System)
 * - Quick access to other settings
 * 
 * Designed to match Bitsgap-style settings panel.
 * 
 * @module components/trading/settings-menu
 */

'use client'

import React from 'react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  DropdownMenuGroup,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { useAppSettings, useTheme, type ThemeMode } from '@/lib/contexts'
import {
  Settings,
  Sun,
  Moon,
  Monitor,
  Check,
  Shield,
  HelpCircle,
  MessageSquare,
  Users,
  LogOut,
  Globe,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface SettingsMenuProps {
  /** Additional CSS classes */
  className?: string
  /** Callback when user wants to log out */
  onLogout?: () => void
}

const THEME_OPTIONS: { value: ThemeMode; label: string; icon: React.ReactNode }[] = [
  { value: 'light', label: 'Light', icon: <Sun className="h-4 w-4" /> },
  { value: 'dark', label: 'Dark', icon: <Moon className="h-4 w-4" /> },
  { value: 'system', label: 'System', icon: <Monitor className="h-4 w-4" /> },
]

/**
 * Settings Menu Component
 * 
 * Full-featured settings dropdown matching Bitsgap design.
 * Includes account mode toggle, theme selection, and navigation.
 * 
 * @example
 * ```tsx
 * <SettingsMenu onLogout={handleLogout} />
 * ```
 */
export function SettingsMenu({
  className,
  onLogout,
}: SettingsMenuProps): JSX.Element {
  const { accountMode, toggleAccountMode, isDemo, isLive } = useAppSettings()
  const { theme, setTheme } = useTheme()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className={cn('h-9 w-9', className)}>
          <Settings className="h-5 w-5" />
          <span className="sr-only">Settings</span>
        </Button>
      </DropdownMenuTrigger>
      
      <DropdownMenuContent align="end" className="w-64">
        {/* Account Mode Section */}
        <DropdownMenuLabel className="flex items-center justify-between">
          <span>Trading Mode</span>
          <Badge
            variant="outline"
            className={cn(
              'font-semibold',
              isDemo && 'bg-blue-500/20 text-blue-400 border-blue-500/30',
              isLive && 'bg-green-500/20 text-green-400 border-green-500/30',
            )}
          >
            {isDemo ? 'Demo' : 'Live'}
          </Badge>
        </DropdownMenuLabel>
        
        <div className="px-2 py-2">
          <div
            className="flex items-center justify-between p-2 rounded-md hover:bg-muted cursor-pointer"
            onClick={toggleAccountMode}
          >
            <div className="flex items-center gap-2">
              <Shield className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm">Demo Mode</span>
            </div>
            <Switch
              checked={isDemo}
              onCheckedChange={toggleAccountMode}
              className="data-[state=checked]:bg-blue-600"
            />
          </div>
          <p className="text-xs text-muted-foreground px-2 mt-1">
            {isDemo
              ? 'Trading with virtual funds. No real money at risk.'
              : 'Trading with real funds. Be careful!'}
          </p>
        </div>

        <DropdownMenuSeparator />

        {/* Theme Section */}
        <DropdownMenuLabel>Appearance</DropdownMenuLabel>
        <DropdownMenuGroup>
          {THEME_OPTIONS.map((option) => (
            <DropdownMenuItem
              key={option.value}
              onClick={() => setTheme(option.value)}
              className="flex items-center justify-between"
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
        </DropdownMenuGroup>

        <DropdownMenuSeparator />

        {/* Quick Links */}
        <DropdownMenuGroup>
          <DropdownMenuItem>
            <Globe className="h-4 w-4 mr-2" />
            <span>Language: EN / USD</span>
          </DropdownMenuItem>
          <DropdownMenuItem>
            <Shield className="h-4 w-4 mr-2" />
            <span>Account settings</span>
          </DropdownMenuItem>
          <DropdownMenuItem>
            <MessageSquare className="h-4 w-4 mr-2" />
            <span>Feedback portal</span>
          </DropdownMenuItem>
          <DropdownMenuItem>
            <HelpCircle className="h-4 w-4 mr-2" />
            <span>Help center</span>
          </DropdownMenuItem>
          <DropdownMenuItem>
            <Users className="h-4 w-4 mr-2" />
            <span>Affiliate program</span>
          </DropdownMenuItem>
        </DropdownMenuGroup>

        {onLogout && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={onLogout} className="text-red-500">
              <LogOut className="h-4 w-4 mr-2" />
              <span>Log out</span>
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export default SettingsMenu
