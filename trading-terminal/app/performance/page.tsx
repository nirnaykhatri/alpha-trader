/**
 * Performance Page
 * 
 * Comprehensive performance analytics and charts.
 * 
 * @module app/performance/page
 */

'use client'

import React from 'react'
import { AppShell } from '@/components/layout'
import { ProtectedRoute } from '@/components/auth'
import { PerformanceCharts } from '@/components/charts'
import { Card, CardContent, CardHeader, CardTitle, Badge } from '@/components/ui'
import { 
  TrendingUp, 
  TrendingDown, 
  BarChart3, 
  Target,
  Award,
  Calendar,
  DollarSign,
  Percent,
} from 'lucide-react'
import { formatCurrency, formatPercent } from '@/lib/utils'

/** Performance summary statistics */
interface PerformanceSummary {
  totalReturn: number
  totalReturnPercent: number
  mtdReturn: number
  mtdReturnPercent: number
  ytdReturn: number
  ytdReturnPercent: number
  bestDay: { date: string; return: number }
  worstDay: { date: string; return: number }
  avgDailyReturn: number
  avgWinSize: number
  avgLossSize: number
  largestWin: number
  largestLoss: number
  consecutiveWins: number
  consecutiveLosses: number
}

/** Mock performance data */
const mockPerformance: PerformanceSummary = {
  totalReturn: 25678.90,
  totalReturnPercent: 25.68,
  mtdReturn: 4532.10,
  mtdReturnPercent: 3.65,
  ytdReturn: 18945.50,
  ytdReturnPercent: 18.95,
  bestDay: { date: '2024-02-15', return: 3245.67 },
  worstDay: { date: '2024-01-22', return: -1876.43 },
  avgDailyReturn: 142.66,
  avgWinSize: 456.78,
  avgLossSize: 234.56,
  largestWin: 3245.67,
  largestLoss: 1876.43,
  consecutiveWins: 8,
  consecutiveLosses: 3,
}

/** Trading statistics */
interface TradingStats {
  totalTrades: number
  winningTrades: number
  losingTrades: number
  winRate: number
  profitFactor: number
  avgTradesPerDay: number
  avgHoldingPeriod: string
  sharpeRatio: number
  sortinoRatio: number
  calmarRatio: number
}

/** Mock trading stats */
const mockStats: TradingStats = {
  totalTrades: 847,
  winningTrades: 527,
  losingTrades: 320,
  winRate: 62.22,
  profitFactor: 1.85,
  avgTradesPerDay: 4.7,
  avgHoldingPeriod: '4h 32m',
  sharpeRatio: 1.92,
  sortinoRatio: 2.45,
  calmarRatio: 3.02,
}

/**
 * SummaryCard Component
 */
function SummaryCard({
  title,
  value,
  subValue,
  icon: Icon,
  trend,
}: {
  title: string
  value: string
  subValue?: string
  icon: React.ElementType
  trend?: 'up' | 'down' | 'neutral'
}) {
  const trendColors = {
    up: 'text-emerald-500',
    down: 'text-red-500',
    neutral: 'text-muted-foreground',
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className={`text-2xl font-bold ${trend ? trendColors[trend] : ''}`}>
          {value}
        </div>
        {subValue && (
          <p className={`text-xs ${trend ? trendColors[trend] : 'text-muted-foreground'}`}>
            {subValue}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

/**
 * StatisticsPanel Component
 */
function StatisticsPanel() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <BarChart3 className="h-5 w-5" />
          Trading Statistics
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-6">
          <div>
            <p className="text-sm text-muted-foreground">Total Trades</p>
            <p className="text-xl font-bold">{mockStats.totalTrades}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Win Rate</p>
            <p className="text-xl font-bold text-emerald-500">{mockStats.winRate}%</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Profit Factor</p>
            <p className="text-xl font-bold">{mockStats.profitFactor}x</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Sharpe Ratio</p>
            <p className="text-xl font-bold">{mockStats.sharpeRatio}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Sortino Ratio</p>
            <p className="text-xl font-bold">{mockStats.sortinoRatio}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Calmar Ratio</p>
            <p className="text-xl font-bold">{mockStats.calmarRatio}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Avg Trades/Day</p>
            <p className="text-xl font-bold">{mockStats.avgTradesPerDay}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Avg Hold Time</p>
            <p className="text-xl font-bold">{mockStats.avgHoldingPeriod}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">W/L Trades</p>
            <p className="text-xl font-bold">
              <span className="text-emerald-500">{mockStats.winningTrades}</span>
              {' / '}
              <span className="text-red-500">{mockStats.losingTrades}</span>
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * RecordsPanel Component
 */
function RecordsPanel() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Award className="h-5 w-5" />
          Records & Extremes
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp className="h-4 w-4 text-emerald-500" />
                <span className="text-sm text-muted-foreground">Best Day</span>
              </div>
              <p className="text-lg font-bold text-emerald-500">
                {formatCurrency(mockPerformance.bestDay.return)}
              </p>
              <p className="text-xs text-muted-foreground">{mockPerformance.bestDay.date}</p>
            </div>
            <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20">
              <div className="flex items-center gap-2 mb-2">
                <TrendingDown className="h-4 w-4 text-red-500" />
                <span className="text-sm text-muted-foreground">Worst Day</span>
              </div>
              <p className="text-lg font-bold text-red-500">
                {formatCurrency(mockPerformance.worstDay.return)}
              </p>
              <p className="text-xs text-muted-foreground">{mockPerformance.worstDay.date}</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">Largest Win</p>
              <p className="font-bold text-emerald-500">{formatCurrency(mockPerformance.largestWin)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Largest Loss</p>
              <p className="font-bold text-red-500">-{formatCurrency(mockPerformance.largestLoss)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Avg Win</p>
              <p className="font-bold text-emerald-500">{formatCurrency(mockPerformance.avgWinSize)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Avg Loss</p>
              <p className="font-bold text-red-500">-{formatCurrency(mockPerformance.avgLossSize)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Max Consecutive Wins</p>
              <p className="font-bold">{mockPerformance.consecutiveWins}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Max Consecutive Losses</p>
              <p className="font-bold">{mockPerformance.consecutiveLosses}</p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Performance Page Component
 */
export default function PerformancePage() {
  return (
    <ProtectedRoute>
      <AppShell>
        <div className="space-y-6">
          {/* Page Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">Performance</h1>
              <p className="text-muted-foreground">
                Analyze your trading performance and metrics
              </p>
            </div>
            <Badge variant="outline" className="gap-1">
              <Calendar className="h-3 w-3" />
              Updated today
            </Badge>
          </div>

          {/* Summary Cards */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <SummaryCard
              title="Total Return"
              value={formatCurrency(mockPerformance.totalReturn)}
              subValue={`+${mockPerformance.totalReturnPercent}%`}
              icon={DollarSign}
              trend="up"
            />
            <SummaryCard
              title="Month to Date"
              value={formatCurrency(mockPerformance.mtdReturn)}
              subValue={`+${mockPerformance.mtdReturnPercent}%`}
              icon={Calendar}
              trend="up"
            />
            <SummaryCard
              title="Year to Date"
              value={formatCurrency(mockPerformance.ytdReturn)}
              subValue={`+${mockPerformance.ytdReturnPercent}%`}
              icon={TrendingUp}
              trend="up"
            />
            <SummaryCard
              title="Avg Daily Return"
              value={formatCurrency(mockPerformance.avgDailyReturn)}
              icon={Target}
              trend="up"
            />
          </div>

          {/* Statistics and Records */}
          <div className="grid gap-6 lg:grid-cols-2">
            <StatisticsPanel />
            <RecordsPanel />
          </div>

          {/* Performance Charts */}
          <PerformanceCharts />
        </div>
      </AppShell>
    </ProtectedRoute>
  )
}
