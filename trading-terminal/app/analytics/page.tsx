/**
 * Bot Analytics Page
 * 
 * Comprehensive analytics dashboard for trading bot performance.
 * Shows PnL history, deal history, profit distribution, and performance metrics.
 * 
 * Similar to Bitsgap's bot analytics feature.
 * 
 * @module app/analytics/page
 */

'use client'

import React, { useState, useMemo } from 'react'
import { AppShell } from '@/components/layout'
import { ProtectedRoute } from '@/components/auth'
import { PageErrorBoundary, SectionErrorBoundary } from '@/components/error-boundary'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  Badge,
  Button,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
  Skeleton,
} from '@/components/ui'
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  BarChart3,
  LineChart,
  PieChart,
  Calendar,
  Clock,
  ArrowUpRight,
  ArrowDownRight,
  Activity,
  Target,
  Percent,
  Filter,
  Download,
  RefreshCw,
  CheckCircle,
  XCircle,
  Minus,
  AlertCircle,
} from 'lucide-react'
import { formatCurrency, formatPercent, cn, getPnLTextColor } from '@/lib/utils'
import { AssetClass, ASSET_CLASS_CONFIG, getDisplaySymbol, createAssetFromSymbol } from '@/lib/types/asset'
import { useAnalytics } from '@/lib/hooks'

// Types for analytics
interface DealRecord {
  id: string
  symbol: string
  assetClass: AssetClass
  quoteSymbol?: string
  type: 'buy' | 'sell'
  side: 'long' | 'short'
  quantity: number
  entryPrice: number
  exitPrice?: number
  pnl?: number
  pnlPercent?: number
  status: 'open' | 'closed' | 'cancelled'
  openedAt: Date
  closedAt?: Date
  dcaLevel?: number
  fees: number
  botId: string
  botName: string
}

interface DailyPnL {
  date: Date
  pnl: number
  trades: number
  wins: number
  losses: number
}

interface AssetPnL {
  assetClass: AssetClass
  pnl: number
  trades: number
  winRate: number
}

// Mock deal history data
const mockDeals: DealRecord[] = [
  {
    id: 'deal-1',
    symbol: 'NVDA',
    assetClass: 'stock',
    type: 'sell',
    side: 'long',
    quantity: 10,
    entryPrice: 875.50,
    exitPrice: 920.30,
    pnl: 448.00,
    pnlPercent: 5.12,
    status: 'closed',
    openedAt: new Date('2025-01-10T09:30:00'),
    closedAt: new Date('2025-01-15T15:45:00'),
    dcaLevel: 2,
    fees: 1.50,
    botId: 'bot-1',
    botName: 'NVDA DCA Long',
  },
  {
    id: 'deal-2',
    symbol: 'BTC',
    assetClass: 'crypto',
    quoteSymbol: 'USD',
    type: 'buy',
    side: 'long',
    quantity: 0.025,
    entryPrice: 95420.00,
    pnl: 185.50,
    pnlPercent: 7.78,
    status: 'open',
    openedAt: new Date('2025-01-12T14:00:00'),
    dcaLevel: 1,
    fees: 4.50,
    botId: 'bot-2',
    botName: 'BTC Accumulator',
  },
  {
    id: 'deal-3',
    symbol: 'EUR',
    assetClass: 'forex',
    quoteSymbol: 'USD',
    type: 'sell',
    side: 'long',
    quantity: 10000,
    entryPrice: 1.0425,
    exitPrice: 1.0485,
    pnl: 60.00,
    pnlPercent: 0.58,
    status: 'closed',
    openedAt: new Date('2025-01-08T08:00:00'),
    closedAt: new Date('2025-01-11T12:30:00'),
    fees: 2.00,
    botId: 'bot-3',
    botName: 'EUR/USD Scalper',
  },
  {
    id: 'deal-4',
    symbol: 'AAPL',
    assetClass: 'stock',
    type: 'sell',
    side: 'long',
    quantity: 25,
    entryPrice: 245.20,
    exitPrice: 238.50,
    pnl: -167.50,
    pnlPercent: -2.73,
    status: 'closed',
    openedAt: new Date('2025-01-05T10:15:00'),
    closedAt: new Date('2025-01-09T14:00:00'),
    dcaLevel: 3,
    fees: 1.00,
    botId: 'bot-1',
    botName: 'AAPL DCA Long',
  },
  {
    id: 'deal-5',
    symbol: 'ETH',
    assetClass: 'crypto',
    quoteSymbol: 'USD',
    type: 'sell',
    side: 'long',
    quantity: 0.5,
    entryPrice: 3280.00,
    exitPrice: 3420.00,
    pnl: 70.00,
    pnlPercent: 4.27,
    status: 'closed',
    openedAt: new Date('2025-01-07T16:00:00'),
    closedAt: new Date('2025-01-13T09:00:00'),
    dcaLevel: 1,
    fees: 3.20,
    botId: 'bot-2',
    botName: 'ETH Accumulator',
  },
  {
    id: 'deal-6',
    symbol: 'GC',
    assetClass: 'commodity',
    quoteSymbol: 'USD',
    type: 'buy',
    side: 'long',
    quantity: 5,
    entryPrice: 2680.50,
    pnl: 125.00,
    pnlPercent: 0.93,
    status: 'open',
    openedAt: new Date('2025-01-14T11:00:00'),
    fees: 5.00,
    botId: 'bot-4',
    botName: 'Gold Hedger',
  },
  {
    id: 'deal-7',
    symbol: 'MSFT',
    assetClass: 'stock',
    type: 'sell',
    side: 'long',
    quantity: 15,
    entryPrice: 415.30,
    exitPrice: 428.75,
    pnl: 201.75,
    pnlPercent: 3.24,
    status: 'closed',
    openedAt: new Date('2025-01-03T09:30:00'),
    closedAt: new Date('2025-01-10T15:30:00'),
    dcaLevel: 2,
    fees: 1.50,
    botId: 'bot-1',
    botName: 'MSFT DCA Long',
  },
]

// Mock daily PnL data
const mockDailyPnL: DailyPnL[] = [
  { date: new Date('2025-01-01'), pnl: 125.50, trades: 3, wins: 2, losses: 1 },
  { date: new Date('2025-01-02'), pnl: -45.20, trades: 2, wins: 0, losses: 2 },
  { date: new Date('2025-01-03'), pnl: 210.00, trades: 4, wins: 3, losses: 1 },
  { date: new Date('2025-01-04'), pnl: 78.30, trades: 2, wins: 2, losses: 0 },
  { date: new Date('2025-01-05'), pnl: -120.00, trades: 3, wins: 1, losses: 2 },
  { date: new Date('2025-01-06'), pnl: 165.75, trades: 3, wins: 2, losses: 1 },
  { date: new Date('2025-01-07'), pnl: 95.00, trades: 2, wins: 2, losses: 0 },
  { date: new Date('2025-01-08'), pnl: 280.50, trades: 5, wins: 4, losses: 1 },
  { date: new Date('2025-01-09'), pnl: -35.00, trades: 2, wins: 1, losses: 1 },
  { date: new Date('2025-01-10'), pnl: 150.25, trades: 3, wins: 2, losses: 1 },
  { date: new Date('2025-01-11'), pnl: 92.00, trades: 2, wins: 2, losses: 0 },
  { date: new Date('2025-01-12'), pnl: 185.00, trades: 4, wins: 3, losses: 1 },
  { date: new Date('2025-01-13'), pnl: -28.50, trades: 2, wins: 1, losses: 1 },
  { date: new Date('2025-01-14'), pnl: 320.00, trades: 5, wins: 4, losses: 1 },
]

/**
 * Performance Summary Cards
 */
function PerformanceSummary({ deals, dailyPnL }: { deals: DealRecord[], dailyPnL: DailyPnL[] }) {
  const closedDeals = deals.filter(d => d.status === 'closed')
  const totalPnL = closedDeals.reduce((sum, d) => sum + (d.pnl || 0), 0)
  const totalTrades = closedDeals.length
  const winningTrades = closedDeals.filter(d => (d.pnl || 0) > 0).length
  const winRate = totalTrades > 0 ? (winningTrades / totalTrades) * 100 : 0
  const avgPnL = totalTrades > 0 ? totalPnL / totalTrades : 0

  // Calculate cumulative PnL for chart
  const cumulativePnL = dailyPnL.reduce<number[]>((acc, day) => {
    const lastValue = acc.length > 0 ? acc[acc.length - 1] : 0
    acc.push(lastValue + day.pnl)
    return acc
  }, [])

  const maxPnL = Math.max(...cumulativePnL, 0)
  const minPnL = Math.min(...cumulativePnL, 0)
  const range = maxPnL - minPnL || 1

  return (
    <div className="grid gap-4 md:grid-cols-4">
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Total PnL</p>
              <p className={cn(
                'text-2xl font-bold',
                getPnLTextColor(totalPnL)
              )}>
                {totalPnL >= 0 ? '+' : ''}{formatCurrency(totalPnL)}
              </p>
              <p className="text-xs text-muted-foreground">From {totalTrades} trades</p>
            </div>
            <div className={cn(
              'h-10 w-10 rounded-full flex items-center justify-center',
              totalPnL >= 0 ? 'bg-emerald-500/10' : 'bg-red-500/10'
            )}>
              {totalPnL >= 0 ? (
                <TrendingUp className="h-5 w-5 text-emerald-500" />
              ) : (
                <TrendingDown className="h-5 w-5 text-red-500" />
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Win Rate</p>
              <p className="text-2xl font-bold">{formatPercent(winRate)}</p>
              <p className="text-xs text-muted-foreground">
                {winningTrades}/{totalTrades} winning
              </p>
            </div>
            <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
              <Target className="h-5 w-5 text-primary" />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Avg PnL/Trade</p>
              <p className={cn(
                'text-2xl font-bold',
                getPnLTextColor(avgPnL)
              )}>
                {avgPnL >= 0 ? '+' : ''}{formatCurrency(avgPnL)}
              </p>
              <p className="text-xs text-muted-foreground">Per closed trade</p>
            </div>
            <div className="h-10 w-10 rounded-full bg-blue-500/10 flex items-center justify-center">
              <BarChart3 className="h-5 w-5 text-blue-500" />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Active Deals</p>
              <p className="text-2xl font-bold">
                {deals.filter(d => d.status === 'open').length}
              </p>
              <p className="text-xs text-muted-foreground">Currently running</p>
            </div>
            <div className="h-10 w-10 rounded-full bg-amber-500/10 flex items-center justify-center">
              <Activity className="h-5 w-5 text-amber-500" />
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * PnL Chart (Simple SVG implementation)
 */
function PnLChart({ dailyPnL }: { dailyPnL: DailyPnL[] }) {
  const width = 100
  const height = 40
  const padding = 2

  // Calculate cumulative PnL
  const cumulativePnL = dailyPnL.reduce<{ date: Date; value: number }[]>((acc, day) => {
    const lastValue = acc.length > 0 ? acc[acc.length - 1].value : 0
    acc.push({ date: day.date, value: lastValue + day.pnl })
    return acc
  }, [])

  const values = cumulativePnL.map(d => d.value)
  const maxValue = Math.max(...values, 0)
  const minValue = Math.min(...values, 0)
  const range = maxValue - minValue || 1

  // Generate path
  const points = cumulativePnL.map((d, i) => {
    const x = padding + (i / (cumulativePnL.length - 1)) * (width - 2 * padding)
    const y = padding + ((maxValue - d.value) / range) * (height - 2 * padding)
    return `${x},${y}`
  }).join(' ')

  const finalValue = cumulativePnL[cumulativePnL.length - 1]?.value || 0
  const isPositive = finalValue >= 0

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Cumulative PnL</span>
          <span className={cn(
            'text-lg',
            getPnLTextColor(finalValue)
          )}>
            {isPositive ? '+' : ''}{formatCurrency(finalValue)}
          </span>
        </CardTitle>
        <CardDescription>Performance over time</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="relative h-48">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-full"
            preserveAspectRatio="none"
          >
            {/* Grid lines */}
            <line x1={padding} y1={height/2} x2={width-padding} y2={height/2} stroke="currentColor" strokeOpacity="0.1" />
            
            {/* Zero line */}
            {minValue < 0 && maxValue > 0 && (
              <line
                x1={padding}
                y1={padding + (maxValue / range) * (height - 2 * padding)}
                x2={width - padding}
                y2={padding + (maxValue / range) * (height - 2 * padding)}
                stroke="currentColor"
                strokeOpacity="0.3"
                strokeDasharray="2,2"
              />
            )}

            {/* Area under curve */}
            <defs>
              <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={isPositive ? '#10b981' : '#ef4444'} stopOpacity="0.3" />
                <stop offset="100%" stopColor={isPositive ? '#10b981' : '#ef4444'} stopOpacity="0" />
              </linearGradient>
            </defs>
            <polygon
              points={`${padding},${height - padding} ${points} ${width - padding},${height - padding}`}
              fill="url(#pnlGradient)"
            />

            {/* Line */}
            <polyline
              points={points}
              fill="none"
              stroke={isPositive ? '#10b981' : '#ef4444'}
              strokeWidth="0.5"
              vectorEffect="non-scaling-stroke"
            />

            {/* End point */}
            <circle
              cx={width - padding}
              cy={padding + ((maxValue - finalValue) / range) * (height - 2 * padding)}
              r="1"
              fill={isPositive ? '#10b981' : '#ef4444'}
            />
          </svg>
        </div>

        {/* Date labels */}
        <div className="flex justify-between text-xs text-muted-foreground mt-2">
          <span>{dailyPnL[0]?.date.toLocaleDateString()}</span>
          <span>{dailyPnL[dailyPnL.length - 1]?.date.toLocaleDateString()}</span>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * PnL by Asset Class
 */
function PnLByAssetClass({ deals }: { deals: DealRecord[] }) {
  const closedDeals = deals.filter(d => d.status === 'closed')
  
  const assetPnL = closedDeals.reduce<Record<AssetClass, { pnl: number; trades: number; wins: number }>>((acc, deal) => {
    if (!acc[deal.assetClass]) {
      acc[deal.assetClass] = { pnl: 0, trades: 0, wins: 0 }
    }
    acc[deal.assetClass].pnl += deal.pnl || 0
    acc[deal.assetClass].trades += 1
    if ((deal.pnl || 0) > 0) acc[deal.assetClass].wins += 1
    return acc
  }, {} as Record<AssetClass, { pnl: number; trades: number; wins: number }>)

  const assetClasses = Object.entries(assetPnL)
    .sort((a, b) => Math.abs(b[1].pnl) - Math.abs(a[1].pnl))

  const maxPnL = Math.max(...assetClasses.map(([, data]) => Math.abs(data.pnl)), 1)

  return (
    <Card>
      <CardHeader>
        <CardTitle>PnL by Asset Class</CardTitle>
        <CardDescription>Performance breakdown by market</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {assetClasses.map(([assetClass, data]) => {
          const config = ASSET_CLASS_CONFIG[assetClass as AssetClass]
          const isPositive = data.pnl >= 0
          const barWidth = (Math.abs(data.pnl) / maxPnL) * 100
          const winRate = data.trades > 0 ? (data.wins / data.trades) * 100 : 0

          return (
            <div key={assetClass} className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{config.icon}</span>
                  <span className="font-medium">{config.label}</span>
                  <Badge variant="outline" className="text-xs">
                    {data.trades} trades
                  </Badge>
                </div>
                <div className="text-right">
                  <span className={cn(
                    'font-bold',
                    getPnLTextColor(data.pnl)
                  )}>
                    {isPositive ? '+' : ''}{formatCurrency(data.pnl)}
                  </span>
                  <p className="text-xs text-muted-foreground">
                    {formatPercent(winRate)} win rate
                  </p>
                </div>
              </div>
              <div className="h-2 bg-muted rounded-full overflow-hidden">
                <div
                  className={cn(
                    'h-full rounded-full transition-all',
                    isPositive ? 'bg-emerald-500' : 'bg-red-500'
                  )}
                  style={{ width: `${barWidth}%` }}
                />
              </div>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}

/**
 * Deal History Table
 */
function DealHistory({ deals }: { deals: DealRecord[] }) {
  const [filter, setFilter] = useState<'all' | 'open' | 'closed'>('all')
  const [assetFilter, setAssetFilter] = useState<AssetClass | 'all'>('all')

  const filteredDeals = useMemo(() => {
    return deals.filter(deal => {
      if (filter !== 'all' && deal.status !== filter) return false
      if (assetFilter !== 'all' && deal.assetClass !== assetFilter) return false
      return true
    }).sort((a, b) => b.openedAt.getTime() - a.openedAt.getTime())
  }, [deals, filter, assetFilter])

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Deal History</CardTitle>
            <CardDescription>All bot trades and their outcomes</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Select value={filter} onValueChange={(v) => setFilter(v as typeof filter)}>
              <SelectTrigger className="w-28">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="open">Open</SelectItem>
                <SelectItem value="closed">Closed</SelectItem>
              </SelectContent>
            </Select>
            <Select value={assetFilter} onValueChange={(v) => setAssetFilter(v as typeof assetFilter)}>
              <SelectTrigger className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Assets</SelectItem>
                {Object.entries(ASSET_CLASS_CONFIG).map(([key, config]) => (
                  <SelectItem key={key} value={key}>
                    <span className="flex items-center gap-2">
                      <span>{config.icon}</span>
                      {config.label}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="outline" size="sm">
              <Download className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b text-left text-sm text-muted-foreground">
                <th className="pb-3 font-medium">Asset</th>
                <th className="pb-3 font-medium">Bot</th>
                <th className="pb-3 font-medium text-right">Entry</th>
                <th className="pb-3 font-medium text-right">Exit</th>
                <th className="pb-3 font-medium text-right">Qty</th>
                <th className="pb-3 font-medium text-right">PnL</th>
                <th className="pb-3 font-medium text-center">Status</th>
                <th className="pb-3 font-medium text-right">Date</th>
              </tr>
            </thead>
            <tbody>
              {filteredDeals.map((deal) => {
                const config = ASSET_CLASS_CONFIG[deal.assetClass]
                const asset = createAssetFromSymbol(deal.symbol, deal.quoteSymbol)
                const displaySymbol = getDisplaySymbol(asset)

                return (
                  <tr key={deal.id} className="border-b last:border-0 hover:bg-muted/50">
                    <td className="py-3">
                      <div className="flex items-center gap-2">
                        <span>{config.icon}</span>
                        <div>
                          <p className="font-medium">{displaySymbol}</p>
                          <p className="text-xs text-muted-foreground capitalize">{deal.side}</p>
                        </div>
                      </div>
                    </td>
                    <td className="py-3 text-sm text-muted-foreground">
                      {deal.botName}
                    </td>
                    <td className="py-3 text-right font-mono text-sm">
                      {formatCurrency(deal.entryPrice)}
                    </td>
                    <td className="py-3 text-right font-mono text-sm">
                      {deal.exitPrice ? formatCurrency(deal.exitPrice) : '-'}
                    </td>
                    <td className="py-3 text-right font-mono text-sm">
                      {deal.quantity}
                    </td>
                    <td className="py-3 text-right">
                      {deal.pnl !== undefined ? (
                        <div>
                          <span className={cn(
                            'font-bold',
                            getPnLTextColor(deal.pnl)
                          )}>
                            {deal.pnl >= 0 ? '+' : ''}{formatCurrency(deal.pnl)}
                          </span>
                          {deal.pnlPercent !== undefined && (
                            <p className={cn(
                              'text-xs',
                              getPnLTextColor(deal.pnl)
                            )}>
                              {deal.pnlPercent >= 0 ? '+' : ''}{formatPercent(deal.pnlPercent)}
                            </p>
                          )}
                        </div>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="py-3 text-center">
                      <Badge variant={deal.status === 'open' ? 'default' : deal.status === 'closed' ? 'secondary' : 'outline'}>
                        {deal.status === 'open' && <Activity className="h-3 w-3 mr-1" />}
                        {deal.status === 'closed' && (deal.pnl || 0) >= 0 && <CheckCircle className="h-3 w-3 mr-1" />}
                        {deal.status === 'closed' && (deal.pnl || 0) < 0 && <XCircle className="h-3 w-3 mr-1" />}
                        {deal.status}
                      </Badge>
                    </td>
                    <td className="py-3 text-right text-sm text-muted-foreground">
                      <div>
                        <p>{deal.openedAt.toLocaleDateString()}</p>
                        {deal.closedAt && (
                          <p className="text-xs">{deal.closedAt.toLocaleDateString()}</p>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {filteredDeals.length === 0 && (
          <div className="text-center py-8 text-muted-foreground">
            <p>No deals found matching the filters</p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/**
 * Skeleton loader for performance summary
 */
function PerformanceSummarySkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {[...Array(4)].map((_, i) => (
        <Card key={i}>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <Skeleton className="h-4 w-24 mb-2" />
                <Skeleton className="h-8 w-28 mb-1" />
                <Skeleton className="h-3 w-16" />
              </div>
              <Skeleton className="h-10 w-10 rounded-full" />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

/**
 * Skeleton loader for charts
 */
function ChartSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-32 mb-2" />
        <Skeleton className="h-4 w-48" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-64 w-full" />
      </CardContent>
    </Card>
  )
}

/**
 * Skeleton loader for deal history
 */
function DealHistorySkeleton() {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <Skeleton className="h-5 w-24" />
          <div className="flex items-center gap-2">
            <Skeleton className="h-8 w-24" />
            <Skeleton className="h-8 w-24" />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="flex items-center justify-between py-3 border-b">
              <div className="flex items-center gap-3">
                <Skeleton className="h-8 w-8 rounded" />
                <div>
                  <Skeleton className="h-4 w-20 mb-1" />
                  <Skeleton className="h-3 w-16" />
                </div>
              </div>
              <Skeleton className="h-4 w-16" />
              <Skeleton className="h-4 w-12" />
              <Skeleton className="h-5 w-16" />
              <Skeleton className="h-4 w-20" />
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Error state component
 */
function AnalyticsError({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <Card className="py-12 border-red-500/50">
      <CardContent className="text-center">
        <div className="h-16 w-16 rounded-full bg-red-500/10 mx-auto flex items-center justify-center mb-4">
          <AlertCircle className="h-8 w-8 text-red-500" />
        </div>
        <h3 className="text-lg font-semibold mb-2">Failed to Load Analytics</h3>
        <p className="text-muted-foreground mb-4 max-w-md mx-auto">
          {error}
        </p>
        <Button onClick={onRetry} variant="outline" className="gap-2">
          <RefreshCw className="h-4 w-4" />
          Try Again
        </Button>
      </CardContent>
    </Card>
  )
}

/**
 * Analytics Page Component
 * 
 * Displays trading analytics with loading, error, and empty states.
 * Uses useAnalytics hook for data fetching. Demo mode requires explicit user opt-in
 * to prevent masking real API failures.
 */
export default function AnalyticsPage() {
  const [timeRange, setTimeRange] = useState('30d')
  const [useDemoMode, setUseDemoMode] = useState(false)
  const { data, isLoading, error, refetch } = useAnalytics()
  
  // Use real data if available, demo data only if explicitly enabled
  const hasRealData = data !== null && (data.deals?.length > 0 || data.dailyPnL?.length > 0)
  const deals = hasRealData ? data.deals : (useDemoMode ? mockDeals : [])
  const dailyPnL = hasRealData ? data.dailyPnL : (useDemoMode ? mockDailyPnL : [])
  const isApiAvailable = hasRealData
  const showEmptyState = !isLoading && !hasRealData && !useDemoMode && !error

  // Exit demo mode when real data becomes available
  React.useEffect(() => {
    if (hasRealData && useDemoMode) {
      setUseDemoMode(false)
    }
  }, [hasRealData, useDemoMode])

  return (
    <ProtectedRoute>
      <PageErrorBoundary pageName="Analytics">
        <AppShell>
          <div className="space-y-6">
            {/* Demo Mode Active Warning */}
            {useDemoMode && !isLoading && (
              <Card className="border-amber-500/50 bg-amber-500/5">
                <CardContent className="flex items-center gap-4 py-4">
                  <div className="h-10 w-10 rounded-full bg-amber-500/10 flex items-center justify-center flex-shrink-0">
                    <AlertCircle className="h-5 w-5 text-amber-500" />
                  </div>
                  <div className="flex-1">
                    <h4 className="font-medium text-amber-700 dark:text-amber-400">Demo Mode Active</h4>
                    <p className="text-sm text-muted-foreground">
                      Showing sample analytics data. This is not your real trading history.
                    </p>
                  </div>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    onClick={() => {
                      setUseDemoMode(false)
                      refetch()
                    }} 
                    className="gap-2"
                  >
                    Exit Demo Mode
                  </Button>
                </CardContent>
              </Card>
            )}

            {/* No Data State - Prompt to enable demo mode */}
            {showEmptyState && (
              <Card className="border-muted">
                <CardContent className="py-12">
                  <div className="flex flex-col items-center justify-center text-center space-y-4">
                    <div className="h-16 w-16 rounded-full bg-muted flex items-center justify-center">
                      <BarChart3 className="h-8 w-8 text-muted-foreground" />
                    </div>
                    <div className="space-y-2">
                      <h3 className="text-lg font-semibold">No Analytics Data</h3>
                      <p className="text-sm text-muted-foreground max-w-md">
                        Unable to connect to the trading API. Check your backend connection
                        or try demo mode to explore the interface.
                      </p>
                    </div>
                    <div className="flex gap-3">
                      <Button variant="outline" onClick={refetch}>
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Retry Connection
                      </Button>
                      <Button onClick={() => setUseDemoMode(true)}>
                        <LineChart className="h-4 w-4 mr-2" />
                        Use Demo Data
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Page Header */}
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-3xl font-bold tracking-tight">Analytics</h1>
                <p className="text-muted-foreground">
                  Track bot performance and trading history
                </p>
              </div>
              <div className="flex items-center gap-2">
                {isApiAvailable && (
                  <Badge variant="outline" className="gap-1 text-green-500 border-green-500/50">
                    <CheckCircle className="h-3 w-3" />
                    Live
                  </Badge>
                )}
                <Select value={timeRange} onValueChange={setTimeRange}>
                  <SelectTrigger className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="7d">Last 7 days</SelectItem>
                    <SelectItem value="30d">Last 30 days</SelectItem>
                    <SelectItem value="90d">Last 90 days</SelectItem>
                    <SelectItem value="ytd">Year to date</SelectItem>
                    <SelectItem value="all">All time</SelectItem>
                  </SelectContent>
                </Select>
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={() => refetch()}
                  disabled={isLoading}
                >
                  <RefreshCw className={cn('h-4 w-4', isLoading && 'animate-spin')} />
                </Button>
                <Button variant="outline" size="sm">
                  <Download className="h-4 w-4 mr-2" />
                  Export
                </Button>
              </div>
            </div>

          {/* Loading State */}
          {isLoading && (
            <>
              <PerformanceSummarySkeleton />
              <div className="grid gap-4 lg:grid-cols-2">
                <ChartSkeleton />
                <ChartSkeleton />
              </div>
              <DealHistorySkeleton />
            </>
          )}

          {/* Error State */}
          {error && !isLoading && (
            <AnalyticsError error={error.message} onRetry={refetch} />
          )}

          {/* Content (shown only when we have data - real or demo) */}
          {!isLoading && !showEmptyState && (deals.length > 0 || dailyPnL.length > 0) && (
            <>
              {/* Performance Summary */}
              <SectionErrorBoundary sectionName="Performance Summary">
                <PerformanceSummary deals={deals} dailyPnL={dailyPnL} />
              </SectionErrorBoundary>

              {/* Charts Row */}
              <div className="grid gap-4 lg:grid-cols-2">
                <SectionErrorBoundary sectionName="P&L Chart" compact>
                  <PnLChart dailyPnL={dailyPnL} />
                </SectionErrorBoundary>
                <SectionErrorBoundary sectionName="P&L by Asset Class" compact>
                  <PnLByAssetClass deals={deals} />
                </SectionErrorBoundary>
              </div>

              {/* Deal History */}
              <SectionErrorBoundary sectionName="Deal History">
                <DealHistory deals={deals} />
              </SectionErrorBoundary>
            </>
          )}
        </div>
        </AppShell>
      </PageErrorBoundary>
    </ProtectedRoute>
  )
}
