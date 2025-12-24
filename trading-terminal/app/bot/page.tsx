/**
 * Bot Controls Page
 * 
 * Central control panel for managing the trading bot.
 * 
 * @module app/bot/page
 */

'use client'

import React from 'react'
import { AppShell } from '@/components/layout'
import { ProtectedRoute } from '@/components/auth'
import { BotControls } from '@/components/trading'
import { Card, CardContent, CardHeader, CardTitle, Badge } from '@/components/ui'
import { 
  Activity, 
  Clock, 
  AlertTriangle, 
  CheckCircle2,
  BarChart3,
  TrendingUp,
  Zap,
  Shield,
} from 'lucide-react'

/** Bot performance metrics */
interface BotMetrics {
  totalTrades: number
  winRate: number
  profitFactor: number
  avgTradeSize: number
  avgHoldTime: string
  maxDrawdown: number
  sharpeRatio: number
  successfulDays: number
  totalDays: number
}

/** Mock bot metrics */
const mockMetrics: BotMetrics = {
  totalTrades: 847,
  winRate: 62.3,
  profitFactor: 1.85,
  avgTradeSize: 2500,
  avgHoldTime: '4h 32m',
  maxDrawdown: 8.5,
  sharpeRatio: 1.92,
  successfulDays: 156,
  totalDays: 180,
}

/** Recent bot activity log */
const recentActivity = [
  { time: '14:32:15', event: 'DCA Layer 2 triggered', symbol: 'NVDA', type: 'info' },
  { time: '14:28:03', event: 'Position opened', symbol: 'AAPL', type: 'success' },
  { time: '14:15:42', event: 'Risk check passed', symbol: 'MSFT', type: 'info' },
  { time: '14:10:18', event: 'Signal received', symbol: 'AMD', type: 'info' },
  { time: '13:58:55', event: 'Take profit hit', symbol: 'TSLA', type: 'success' },
  { time: '13:45:22', event: 'Stop loss triggered', symbol: 'META', type: 'warning' },
]

/**
 * MetricCard Component
 */
function MetricCard({
  title,
  value,
  icon: Icon,
  description,
  variant = 'default',
}: {
  title: string
  value: string | number
  icon: React.ElementType
  description?: string
  variant?: 'default' | 'success' | 'warning' | 'danger'
}) {
  const variantStyles = {
    default: 'bg-primary/10 text-primary',
    success: 'bg-emerald-500/10 text-emerald-500',
    warning: 'bg-yellow-500/10 text-yellow-500',
    danger: 'bg-red-500/10 text-red-500',
  }

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold mt-1">{value}</p>
            {description && (
              <p className="text-xs text-muted-foreground mt-1">{description}</p>
            )}
          </div>
          <div className={`h-10 w-10 rounded-lg flex items-center justify-center ${variantStyles[variant]}`}>
            <Icon className="h-5 w-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * ActivityLog Component
 * 
 * Displays recent bot activity.
 */
function ActivityLog() {
  const typeStyles = {
    info: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
    success: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
    warning: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
    error: 'bg-red-500/10 text-red-500 border-red-500/20',
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Activity Log
          </CardTitle>
          <Badge variant="outline" className="gap-1">
            <Clock className="h-3 w-3" />
            Live
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {recentActivity.map((activity, index) => (
            <div 
              key={index}
              className={`flex items-center gap-3 p-3 rounded-lg border ${typeStyles[activity.type as keyof typeof typeStyles]}`}
            >
              <div className="flex-shrink-0 w-16 text-xs font-mono">
                {activity.time}
              </div>
              <div className="flex-1">
                <span className="font-medium">{activity.event}</span>
                {activity.symbol && (
                  <span className="ml-2 px-2 py-0.5 bg-background rounded text-xs font-medium">
                    {activity.symbol}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * PerformanceSummary Component
 * 
 * Shows key performance indicators.
 */
function PerformanceSummary() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <BarChart3 className="h-5 w-5" />
          Performance Summary
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Win Rate */}
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-muted-foreground">Win Rate</span>
              <span className="font-medium">{mockMetrics.winRate}%</span>
            </div>
            <div className="h-2 bg-muted rounded-full overflow-hidden">
              <div 
                className="h-full bg-emerald-500 rounded-full"
                style={{ width: `${mockMetrics.winRate}%` }}
              />
            </div>
          </div>

          {/* Profit Factor */}
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-muted-foreground">Profit Factor</span>
              <span className="font-medium">{mockMetrics.profitFactor}x</span>
            </div>
            <div className="h-2 bg-muted rounded-full overflow-hidden">
              <div 
                className="h-full bg-blue-500 rounded-full"
                style={{ width: `${Math.min(mockMetrics.profitFactor * 33, 100)}%` }}
              />
            </div>
          </div>

          {/* Successful Days */}
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-muted-foreground">Successful Days</span>
              <span className="font-medium">{mockMetrics.successfulDays}/{mockMetrics.totalDays}</span>
            </div>
            <div className="h-2 bg-muted rounded-full overflow-hidden">
              <div 
                className="h-full bg-purple-500 rounded-full"
                style={{ width: `${(mockMetrics.successfulDays / mockMetrics.totalDays) * 100}%` }}
              />
            </div>
          </div>

          {/* Max Drawdown */}
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-muted-foreground">Max Drawdown</span>
              <span className="font-medium text-red-500">-{mockMetrics.maxDrawdown}%</span>
            </div>
            <div className="h-2 bg-muted rounded-full overflow-hidden">
              <div 
                className="h-full bg-red-500 rounded-full"
                style={{ width: `${mockMetrics.maxDrawdown * 5}%` }}
              />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Bot Controls Page Component
 */
export default function BotPage() {
  return (
    <ProtectedRoute>
      <AppShell>
        <div className="space-y-6">
          {/* Page Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">Bot Controls</h1>
              <p className="text-muted-foreground">
                Monitor and control your trading bot
              </p>
            </div>
            <Badge variant="success" className="gap-1">
              <CheckCircle2 className="h-3 w-3" />
              System Healthy
            </Badge>
          </div>

          {/* Metrics Grid */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              title="Total Trades"
              value={mockMetrics.totalTrades.toLocaleString()}
              icon={BarChart3}
              description="All time"
            />
            <MetricCard
              title="Win Rate"
              value={`${mockMetrics.winRate}%`}
              icon={TrendingUp}
              variant="success"
              description="Last 30 days"
            />
            <MetricCard
              title="Sharpe Ratio"
              value={mockMetrics.sharpeRatio}
              icon={Zap}
              variant="success"
              description="Risk-adjusted return"
            />
            <MetricCard
              title="Max Drawdown"
              value={`-${mockMetrics.maxDrawdown}%`}
              icon={Shield}
              variant="warning"
              description="Worst decline"
            />
          </div>

          {/* Main Content */}
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Bot Controls Panel */}
            <BotControls />
            
            {/* Performance Summary */}
            <PerformanceSummary />
          </div>

          {/* Activity Log */}
          <ActivityLog />
        </div>
      </AppShell>
    </ProtectedRoute>
  )
}
