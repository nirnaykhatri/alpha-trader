/**
 * Main Application Layout with Sidebar Navigation
 * 
 * Professional trading terminal layout with responsive sidebar,
 * header with user menu, and real-time status indicators.
 * 
 * @module components/layout/app-shell
 */

'use client'

import React, { useState, ReactNode } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'
import { useAuth } from '@/components/auth'
import { useAppSettings } from '@/lib/contexts'
import { useBotStatus } from '@/lib/hooks/use-bot-status'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import { SettingsMenu, AccountModeToggle } from '@/components/trading'
import {
  LayoutDashboard,
  TrendingUp,
  ShoppingCart,
  History,
  Settings,
  BarChart3,
  Wallet,
  Bot,
  ChevronLeft,
  ChevronRight,
  Bell,
  Moon,
  Sun,
  LogOut,
  User,
  Menu,
  X,
  Activity,
  AlertTriangle,
  CheckCircle,
  XCircle,
  PieChart,
  Link2,
  LineChart,
  BookOpen,
} from 'lucide-react'

interface NavItem {
  title: string
  href: string
  icon: React.ReactNode
  badge?: string | number
  badgeVariant?: 'default' | 'success' | 'danger' | 'warning'
}

const navItems: NavItem[] = [
  {
    title: 'Dashboard',
    href: '/',
    icon: <LayoutDashboard className="h-5 w-5" />,
  },
  {
    title: 'Portfolio',
    href: '/portfolio',
    icon: <PieChart className="h-5 w-5" />,
  },
  {
    title: 'Positions',
    href: '/positions',
    icon: <TrendingUp className="h-5 w-5" />,
  },
  {
    title: 'New Order',
    href: '/orders/new',
    icon: <ShoppingCart className="h-5 w-5" />,
  },
  {
    title: 'Order History',
    href: '/orders',
    icon: <History className="h-5 w-5" />,
  },
  {
    title: 'Trading Bots',
    href: '/bots',
    icon: <Bot className="h-5 w-5" />,
  },
  {
    title: 'Bot Strategies',
    href: '/strategies',
    icon: <BookOpen className="h-5 w-5" />,
  },
  {
    title: 'Analytics',
    href: '/analytics',
    icon: <LineChart className="h-5 w-5" />,
  },
  {
    title: 'Brokers',
    href: '/brokers',
    icon: <Link2 className="h-5 w-5" />,
  },
  {
    title: 'Fund Management',
    href: '/funds',
    icon: <Wallet className="h-5 w-5" />,
  },
  {
    title: 'Configuration',
    href: '/config',
    icon: <Settings className="h-5 w-5" />,
  },
]

/** Bot status for app shell display */
interface BotStatusDisplay {
  status: 'running' | 'paused' | 'stopped' | 'error' | 'created' | 'completed' | 'stopping' | 'checking'
  message?: string
}

interface AppShellProps {
  children: ReactNode
  botStatus?: BotStatusDisplay
}

/**
 * Status Indicator Component
 */
function StatusIndicator({ status }: { status: BotStatusDisplay['status'] }) {
  const statusConfig = {
    checking: { color: 'bg-muted-foreground', icon: AlertTriangle, label: 'Checking...' },
    created: { color: 'bg-muted-foreground', icon: AlertTriangle, label: 'Created' },
    running: { color: 'bg-profit', icon: CheckCircle, label: 'Running' },
    paused: { color: 'bg-warning', icon: AlertTriangle, label: 'Paused' },
    stopping: { color: 'bg-warning', icon: AlertTriangle, label: 'Stopping' },
    stopped: { color: 'bg-muted-foreground', icon: XCircle, label: 'Stopped' },
    completed: { color: 'bg-profit', icon: CheckCircle, label: 'Completed' },
    error: { color: 'bg-loss', icon: AlertTriangle, label: 'Error' },
  }

  const config = statusConfig[status]
  const Icon = config.icon

  return (
    <div className="flex items-center gap-2">
      <div className={cn('h-2 w-2 rounded-full animate-pulse', config.color)} />
      <span className="text-xs font-medium">{config.label}</span>
    </div>
  )
}

/**
 * Sidebar Navigation Component
 */
function Sidebar({
  collapsed,
  onToggle,
  botStatus,
}: {
  collapsed: boolean
  onToggle: () => void
  botStatus: BotStatusDisplay
}) {
  const pathname = usePathname()

  return (
    <aside
      className={cn(
        'fixed left-0 top-0 z-40 h-screen border-r border-border/50 bg-card/50 backdrop-blur-xl transition-all duration-300 ease-in-out',
        collapsed ? 'w-16' : 'w-64'
      )}
    >
      <div className="flex h-full flex-col">
        {/* Logo */}
        <div className="flex h-16 items-center justify-between border-b border-border/50 px-4">
          {!collapsed && (
            <Link href="/" className="flex items-center gap-2">
              <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
                <Activity className="h-5 w-5 text-primary-foreground" />
              </div>
              <span className="font-bold text-lg">Alpha Trader</span>
            </Link>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggle}
            className={cn('h-8 w-8', collapsed && 'mx-auto')}
          >
            {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </Button>
        </div>

        {/* Navigation */}
        <ScrollArea className="flex-1 py-4">
          <nav className="space-y-1 px-2">
            {navItems.map((item) => {
              const isActive = pathname === item.href
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200',
                    isActive
                      ? 'bg-primary text-primary-foreground shadow-md'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground',
                    collapsed && 'justify-center px-2'
                  )}
                  title={collapsed ? item.title : undefined}
                >
                  {item.icon}
                  {!collapsed && (
                    <>
                      <span className="flex-1">{item.title}</span>
                      {item.badge && (
                        <Badge variant={item.badgeVariant || 'default'} className="h-5 text-xs">
                          {item.badge}
                        </Badge>
                      )}
                    </>
                  )}
                </Link>
              )
            })}
          </nav>
        </ScrollArea>

        {/* Bot Status */}
        <div className="border-t border-border/50 p-4">
          {!collapsed ? (
            <div className="rounded-lg bg-muted/50 p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-muted-foreground">Bot Status</span>
                <StatusIndicator status={botStatus.status} />
              </div>
              {botStatus.message && (
                <p className="text-xs text-muted-foreground truncate">{botStatus.message}</p>
              )}
            </div>
          ) : (
            <div className="flex justify-center">
              <div
                className={cn(
                  'h-3 w-3 rounded-full',
                  botStatus.status === 'running' && 'bg-profit animate-pulse',
                  botStatus.status === 'paused' && 'bg-warning',
                  botStatus.status === 'stopped' && 'bg-muted-foreground',
                  botStatus.status === 'checking' && 'bg-muted-foreground animate-pulse',
                  botStatus.status === 'error' && 'bg-loss animate-pulse'
                )}
                title={`Bot ${botStatus.status}`}
              />
            </div>
          )}
        </div>
      </div>
    </aside>
  )
}

/**
 * Header Component with User Menu and Settings
 */
function Header({ sidebarCollapsed }: { sidebarCollapsed: boolean }) {
  const { userName, userEmail, logout, isAuthenticated } = useAuth()
  const { accountMode } = useAppSettings()

  const initials = userName
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)

  return (
    <header
      className={cn(
        'fixed top-0 right-0 z-30 h-16 border-b border-border/50 bg-background/80 backdrop-blur-xl transition-all duration-300',
        sidebarCollapsed ? 'left-16' : 'left-64'
      )}
    >
      <div className="flex h-full items-center justify-between px-6">
        {/* Breadcrumb / Page Title */}
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold">Trading Terminal</h1>
          {/* Account Mode Badge */}
          <Badge 
            variant={accountMode === 'demo' ? 'secondary' : 'default'}
            className={cn(
              'text-xs font-medium uppercase',
              accountMode === 'demo' 
                ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' 
                : 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
            )}
          >
            {accountMode}
          </Badge>
        </div>

        {/* Right Actions */}
        <div className="flex items-center gap-2">
          {/* Demo/Live Toggle (visible on larger screens) */}
          <div className="hidden md:block">
            <AccountModeToggle size="sm" showLabel={false} />
          </div>

          {/* Notifications */}
          <Button variant="ghost" size="icon" className="relative">
            <Bell className="h-5 w-5" />
            <span className="absolute -top-1 -right-1 h-4 w-4 rounded-full bg-loss text-[10px] font-bold text-white flex items-center justify-center">
              3
            </span>
          </Button>

          {/* Settings Menu (includes theme, demo mode for mobile, etc.) */}
          <SettingsMenu />

          <Separator orientation="vertical" className="h-6" />

          {/* User Menu */}
          {isAuthenticated && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="flex items-center gap-2 px-2">
                  <Avatar className="h-8 w-8">
                    <AvatarImage src="" alt={userName} />
                    <AvatarFallback className="bg-primary text-primary-foreground text-xs">
                      {initials}
                    </AvatarFallback>
                  </Avatar>
                  <div className="hidden md:block text-left">
                    <p className="text-sm font-medium">{userName}</p>
                    <p className="text-xs text-muted-foreground">{userEmail}</p>
                  </div>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel>My Account</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem>
                  <User className="mr-2 h-4 w-4" />
                  <span>Profile</span>
                </DropdownMenuItem>
                <DropdownMenuItem>
                  <Settings className="mr-2 h-4 w-4" />
                  <span>Settings</span>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={logout} className="text-loss focus:text-loss">
                  <LogOut className="mr-2 h-4 w-4" />
                  <span>Log out</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>
    </header>
  )
}

/**
 * Mobile Navigation Component
 */
function MobileNav({ botStatus }: { botStatus: BotStatusDisplay }) {
  const [isOpen, setIsOpen] = useState(false)
  const pathname = usePathname()

  return (
    <>
      {/* Mobile Header */}
      <div className="fixed top-0 left-0 right-0 z-50 flex h-16 items-center justify-between border-b border-border/50 bg-background/80 backdrop-blur-xl px-4 md:hidden">
        <Link href="/" className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
            <Activity className="h-5 w-5 text-primary-foreground" />
          </div>
          <span className="font-bold">Alpha Trader</span>
        </Link>
        <Button variant="ghost" size="icon" onClick={() => setIsOpen(!isOpen)}>
          {isOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </Button>
      </div>

      {/* Mobile Menu Overlay */}
      {isOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="fixed inset-0 bg-background/80 backdrop-blur-sm" onClick={() => setIsOpen(false)} />
          <nav className="fixed top-16 left-0 right-0 bottom-0 bg-background border-t border-border/50 overflow-y-auto">
            <div className="p-4 space-y-2">
              {navItems.map((item) => {
                const isActive = pathname === item.href
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setIsOpen(false)}
                    className={cn(
                      'flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                    )}
                  >
                    {item.icon}
                    <span>{item.title}</span>
                  </Link>
                )
              })}
            </div>
            <div className="p-4 border-t border-border/50">
              <div className="rounded-lg bg-muted/50 p-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Bot Status</span>
                  <StatusIndicator status={botStatus.status} />
                </div>
              </div>
            </div>
          </nav>
        </div>
      )}
    </>
  )
}

/**
 * App Shell Component
 * 
 * Main layout wrapper that provides consistent navigation and structure
 * across all pages of the trading terminal.
 * 
 * @param {AppShellProps} props - Component props
 * @returns {JSX.Element} Complete app layout
 */
export function AppShell({
  children,
  botStatus: botStatusProp,
}: AppShellProps): JSX.Element {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const { botStatus: fetchedStatus } = useBotStatus()
  
  // Use prop if provided, otherwise use fetched status from health check
  const botStatus = botStatusProp ?? fetchedStatus

  return (
    <div className="min-h-screen bg-background">
      {/* Desktop Sidebar */}
      <div className="hidden md:block">
        <Sidebar
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
          botStatus={botStatus}
        />
        <Header sidebarCollapsed={sidebarCollapsed} />
      </div>

      {/* Mobile Navigation */}
      <MobileNav botStatus={botStatus} />

      {/* Main Content */}
      <main
        className={cn(
          'min-h-screen pt-16 transition-all duration-300',
          'md:pt-16',
          sidebarCollapsed ? 'md:pl-16' : 'md:pl-64'
        )}
      >
        <div className="container mx-auto p-6">{children}</div>
      </main>
    </div>
  )
}

export default AppShell
