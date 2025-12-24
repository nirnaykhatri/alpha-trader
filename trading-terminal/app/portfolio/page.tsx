/**
 * Portfolio Page
 * 
 * Comprehensive portfolio overview with asset allocation, distribution charts,
 * and multi-asset class support (stocks, forex, crypto, commodities).
 * 
 * @module app/portfolio/page
 */

'use client'

import React, { useState, useMemo } from 'react'
import { AppShell } from '@/components/layout'
import { ProtectedRoute } from '@/components/auth'
import { PageErrorBoundary, SectionErrorBoundary } from '@/components/error-boundary'
import { Card, CardContent, CardHeader, CardTitle, Badge, Button, Skeleton } from '@/components/ui'
import {
  PieChart,
  Wallet,
  TrendingUp,
  TrendingDown,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  Filter,
  MoreHorizontal,
  Briefcase,
  DollarSign,
  BarChart3,
  Target,
  AlertCircle,
} from 'lucide-react'
import { formatCurrency, formatPercent, formatAssetPrice, cn, getPnLTextColor } from '@/lib/utils'
import {
  AssetClass,
  AssetPosition,
  AssetAllocation,
  ASSET_CLASS_CONFIG,
  createAssetFromSymbol,
  getDisplaySymbol,
} from '@/lib/types/asset'
import { usePortfolio } from '@/lib/hooks'

// ============================================================================
// Constants
// ============================================================================

/** Show prominent warning when API is unavailable */
const SHOW_API_WARNING = true

// Mock data for portfolio positions across asset classes
const mockPortfolioPositions: AssetPosition[] = [
  // Stocks
  {
    asset: createAssetFromSymbol('AAPL', 'Apple Inc.'),
    quantity: 50,
    avgCost: 178.50,
    currentPrice: 182.45,
    marketValue: 9122.50,
    unrealizedPnL: 197.50,
    unrealizedPnLPercent: 2.21,
    dayPnL: 45.23,
    dayPnLPercent: 0.50,
    side: 'long',
    openDate: '2024-03-10',
    dcaLayers: 2,
    riskScore: 'low',
    portfolioWeight: 12.5,
  },
  {
    asset: createAssetFromSymbol('NVDA', 'NVIDIA Corporation'),
    quantity: 25,
    avgCost: 680.00,
    currentPrice: 725.30,
    marketValue: 18132.50,
    unrealizedPnL: 1132.50,
    unrealizedPnLPercent: 6.66,
    dayPnL: 325.00,
    dayPnLPercent: 1.83,
    side: 'long',
    openDate: '2024-03-08',
    dcaLayers: 3,
    riskScore: 'medium',
    portfolioWeight: 24.8,
  },
  {
    asset: createAssetFromSymbol('MSFT', 'Microsoft Corporation'),
    quantity: 40,
    avgCost: 405.00,
    currentPrice: 418.92,
    marketValue: 16756.80,
    unrealizedPnL: 556.80,
    unrealizedPnLPercent: 3.44,
    dayPnL: 112.40,
    dayPnLPercent: 0.67,
    side: 'long',
    openDate: '2024-03-05',
    dcaLayers: 1,
    riskScore: 'low',
    portfolioWeight: 22.9,
  },
  // Crypto
  {
    asset: createAssetFromSymbol('BTC/USD', 'Bitcoin'),
    quantity: 0.5,
    avgCost: 42000,
    currentPrice: 43500,
    marketValue: 21750,
    unrealizedPnL: 750,
    unrealizedPnLPercent: 3.57,
    dayPnL: 425.00,
    dayPnLPercent: 1.99,
    side: 'long',
    openDate: '2024-02-15',
    dcaLayers: 4,
    riskScore: 'high',
    portfolioWeight: 29.7,
  },
  {
    asset: createAssetFromSymbol('ETH/USD', 'Ethereum'),
    quantity: 5,
    avgCost: 2200,
    currentPrice: 2350,
    marketValue: 11750,
    unrealizedPnL: 750,
    unrealizedPnLPercent: 6.82,
    dayPnL: 187.50,
    dayPnLPercent: 1.62,
    side: 'long',
    openDate: '2024-02-20',
    dcaLayers: 2,
    riskScore: 'medium',
    portfolioWeight: 16.1,
  },
  // Forex
  {
    asset: createAssetFromSymbol('EUR/USD', 'Euro / US Dollar'),
    quantity: 10000,
    avgCost: 1.0850,
    currentPrice: 1.0920,
    marketValue: 10920,
    unrealizedPnL: 70,
    unrealizedPnLPercent: 0.65,
    dayPnL: 15.00,
    dayPnLPercent: 0.14,
    side: 'long',
    openDate: '2024-03-12',
    dcaLayers: 0,
    riskScore: 'low',
    portfolioWeight: 14.9,
  },
  // Commodities
  {
    asset: createAssetFromSymbol('GC', 'Gold Futures', { assetClass: 'commodity', name: 'Gold' }),
    quantity: 10,
    avgCost: 2050,
    currentPrice: 2085,
    marketValue: 20850,
    unrealizedPnL: 350,
    unrealizedPnLPercent: 1.71,
    dayPnL: 125.00,
    dayPnLPercent: 0.60,
    side: 'long',
    openDate: '2024-03-01',
    dcaLayers: 1,
    riskScore: 'low',
    portfolioWeight: 28.5,
  },
]

/**
 * Calculate allocations from positions
 */
function calculateAllocations(positions: AssetPosition[]): AssetAllocation[] {
  const allocationMap = new Map<AssetClass, AssetAllocation>()
  const totalValue = positions.reduce((sum, p) => sum + p.marketValue, 0)

  positions.forEach((position) => {
    const assetClass = position.asset.assetClass
    const existing = allocationMap.get(assetClass)
    const config = ASSET_CLASS_CONFIG[assetClass]

    if (existing) {
      existing.value += position.marketValue
      existing.positions += 1
      existing.unrealizedPnL += position.unrealizedPnL
    } else {
      allocationMap.set(assetClass, {
        assetClass,
        value: position.marketValue,
        percentage: 0,
        positions: 1,
        unrealizedPnL: position.unrealizedPnL,
        color: config.color.replace('text-', ''),
      })
    }
  })

  // Calculate percentages
  const allocations = Array.from(allocationMap.values())
  allocations.forEach((a) => {
    a.percentage = (a.value / totalValue) * 100
  })

  return allocations.sort((a, b) => b.value - a.value)
}

/**
 * Portfolio Summary Stats
 */
function PortfolioSummary({ positions }: { positions: AssetPosition[] }) {
  const totalValue = positions.reduce((sum, p) => sum + p.marketValue, 0)
  const totalPnL = positions.reduce((sum, p) => sum + p.unrealizedPnL, 0)
  const totalDayPnL = positions.reduce((sum, p) => sum + p.dayPnL, 0)
  const totalCost = positions.reduce((sum, p) => sum + p.avgCost * p.quantity, 0)
  const totalPnLPercent = (totalPnL / totalCost) * 100
  const dayPnLPercent = (totalDayPnL / (totalValue - totalDayPnL)) * 100

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Portfolio Value</p>
              <p className="text-2xl font-bold">{formatCurrency(totalValue)}</p>
              <p className="text-xs text-muted-foreground mt-1">
                Across {positions.length} positions
              </p>
            </div>
            <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
              <Wallet className="h-6 w-6 text-primary" />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Total P&L</p>
              <p className={cn('text-2xl font-bold', getPnLTextColor(totalPnL))}>
                {formatCurrency(totalPnL)}
              </p>
              <p className={cn('text-xs flex items-center gap-1', getPnLTextColor(totalPnL))}>
                {totalPnL >= 0 ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                {formatPercent(totalPnLPercent)}
              </p>
            </div>
            <div className={cn('h-12 w-12 rounded-full flex items-center justify-center', 
              totalPnL >= 0 ? 'bg-emerald-500/10' : 'bg-red-500/10')}>
              {totalPnL >= 0 ? (
                <TrendingUp className="h-6 w-6 text-emerald-500" />
              ) : (
                <TrendingDown className="h-6 w-6 text-red-500" />
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Today's P&L</p>
              <p className={cn('text-2xl font-bold', getPnLTextColor(totalDayPnL))}>
                {formatCurrency(totalDayPnL)}
              </p>
              <p className={cn('text-xs flex items-center gap-1', getPnLTextColor(totalDayPnL))}>
                {totalDayPnL >= 0 ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                {formatPercent(dayPnLPercent)}
              </p>
            </div>
            <div className={cn('h-12 w-12 rounded-full flex items-center justify-center',
              totalDayPnL >= 0 ? 'bg-emerald-500/10' : 'bg-red-500/10')}>
              <BarChart3 className={cn('h-6 w-6', getPnLTextColor(totalDayPnL))} />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Buying Power</p>
              <p className="text-2xl font-bold">{formatCurrency(45000)}</p>
              <p className="text-xs text-muted-foreground mt-1">Available to trade</p>
            </div>
            <div className="h-12 w-12 rounded-full bg-blue-500/10 flex items-center justify-center">
              <DollarSign className="h-6 w-6 text-blue-500" />
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * Asset Allocation Pie Chart (Visual representation)
 */
function AllocationChart({ allocations }: { allocations: AssetAllocation[] }) {
  const colors = {
    stock: '#3b82f6',    // blue
    etf: '#6366f1',      // indigo
    crypto: '#f97316',   // orange
    forex: '#10b981',    // emerald
    commodity: '#f59e0b', // amber
    index: '#8b5cf6',    // purple
  }

  // Calculate pie segments
  let currentAngle = 0
  const segments = allocations.map((allocation) => {
    const startAngle = currentAngle
    const angle = (allocation.percentage / 100) * 360
    currentAngle += angle
    
    // Calculate SVG arc path
    const startRad = (startAngle - 90) * (Math.PI / 180)
    const endRad = (startAngle + angle - 90) * (Math.PI / 180)
    const radius = 80
    const centerX = 100
    const centerY = 100
    
    const x1 = centerX + radius * Math.cos(startRad)
    const y1 = centerY + radius * Math.sin(startRad)
    const x2 = centerX + radius * Math.cos(endRad)
    const y2 = centerY + radius * Math.sin(endRad)
    
    const largeArc = angle > 180 ? 1 : 0
    
    return {
      ...allocation,
      path: `M ${centerX} ${centerY} L ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2} Z`,
      color: colors[allocation.assetClass],
    }
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <PieChart className="h-5 w-5" />
          Asset Allocation
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col md:flex-row items-center gap-8">
          {/* Pie Chart SVG with accessibility attributes */}
          <div className="relative">
            <svg 
              viewBox="0 0 200 200" 
              className="w-48 h-48"
              role="img"
              aria-label={`Asset allocation pie chart showing ${allocations.length} asset classes`}
            >
              <title>Asset Allocation Distribution</title>
              <desc>
                Pie chart showing portfolio distribution across asset classes: 
                {allocations.map(a => `${ASSET_CLASS_CONFIG[a.assetClass].label} ${a.percentage.toFixed(1)}%`).join(', ')}
              </desc>
              {segments.map((segment, index) => (
                <path
                  key={index}
                  d={segment.path}
                  fill={segment.color}
                  className="transition-opacity hover:opacity-80 cursor-pointer"
                  role="presentation"
                  aria-hidden="true"
                />
              ))}
              {/* Center circle for donut effect */}
              <circle cx="100" cy="100" r="50" fill="hsl(var(--background))" aria-hidden="true" />
              <text x="100" y="95" textAnchor="middle" className="text-xs fill-muted-foreground" aria-hidden="true">
                Total
              </text>
              <text x="100" y="112" textAnchor="middle" className="text-sm font-bold fill-foreground" aria-hidden="true">
                {allocations.length} Classes
              </text>
            </svg>
          </div>

          {/* Legend */}
          <div className="flex-1 space-y-3">
            {allocations.map((allocation) => {
              const config = ASSET_CLASS_CONFIG[allocation.assetClass]
              return (
                <div key={allocation.assetClass} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div 
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: colors[allocation.assetClass] }}
                    />
                    <span className="text-sm font-medium">{config.label}</span>
                    <Badge variant="secondary" className="text-xs">
                      {allocation.positions}
                    </Badge>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-medium">{formatCurrency(allocation.value)}</p>
                    <p className="text-xs text-muted-foreground">
                      {allocation.percentage.toFixed(1)}%
                    </p>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Position Row Component
 */
function PositionRow({ position }: { position: AssetPosition }) {
  const config = ASSET_CLASS_CONFIG[position.asset.assetClass]
  const isProfitable = position.unrealizedPnL >= 0
  const isDayProfitable = position.dayPnL >= 0

  return (
    <div className="flex items-center justify-between p-4 hover:bg-muted/50 rounded-lg transition-colors">
      <div className="flex items-center gap-4">
        {/* Asset Icon/Logo */}
        <div className={cn('w-10 h-10 rounded-lg flex items-center justify-center text-lg', config.bgColor)}>
          {config.icon}
        </div>
        
        {/* Asset Info */}
        <div>
          <div className="flex items-center gap-2">
            <span className="font-semibold">{getDisplaySymbol(position.asset)}</span>
            <Badge variant="outline" className="text-xs">
              {position.side.toUpperCase()}
            </Badge>
            <Badge variant="secondary" className={cn('text-xs', config.color)}>
              {config.label}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">{position.asset.name}</p>
        </div>
      </div>

      {/* Position Details */}
      <div className="hidden md:flex items-center gap-8">
        <div className="text-right">
          <p className="text-sm text-muted-foreground">Quantity</p>
          <p className="font-medium">{position.quantity}</p>
        </div>
        <div className="text-right">
          <p className="text-sm text-muted-foreground">Avg Cost</p>
          <p className="font-medium">{formatAssetPrice(position.avgCost, position.asset)}</p>
        </div>
        <div className="text-right">
          <p className="text-sm text-muted-foreground">Current</p>
          <p className={cn('font-medium', getPnLTextColor(position.unrealizedPnL))}>
            {formatAssetPrice(position.currentPrice, position.asset)}
          </p>
        </div>
        <div className="text-right">
          <p className="text-sm text-muted-foreground">Market Value</p>
          <p className="font-medium">{formatCurrency(position.marketValue)}</p>
        </div>
      </div>

      {/* P&L */}
      <div className="text-right">
        <p className={cn('font-bold', getPnLTextColor(position.unrealizedPnL))}>
          {formatCurrency(position.unrealizedPnL)}
        </p>
        <p className={cn('text-xs flex items-center justify-end gap-1', 
          getPnLTextColor(position.unrealizedPnL))}>
          {isProfitable ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
          {formatPercent(position.unrealizedPnLPercent)}
        </p>
      </div>

      {/* Actions */}
      <Button variant="ghost" size="sm" className="ml-4">
        <MoreHorizontal className="h-4 w-4" />
      </Button>
    </div>
  )
}

/**
 * Holdings List Component
 */
function HoldingsList({ positions }: { positions: AssetPosition[] }) {
  const [filter, setFilter] = useState<AssetClass | 'all'>('all')
  const [sortBy, setSortBy] = useState<'value' | 'pnl' | 'change'>('value')

  const filteredPositions = useMemo(() => {
    let filtered = filter === 'all' 
      ? positions 
      : positions.filter(p => p.asset.assetClass === filter)
    
    return filtered.sort((a, b) => {
      switch (sortBy) {
        case 'value': return b.marketValue - a.marketValue
        case 'pnl': return b.unrealizedPnL - a.unrealizedPnL
        case 'change': return b.unrealizedPnLPercent - a.unrealizedPnLPercent
        default: return 0
      }
    })
  }, [positions, filter, sortBy])

  const assetClasses = Array.from(new Set(positions.map(p => p.asset.assetClass)))

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <Briefcase className="h-5 w-5" />
            Holdings
          </CardTitle>
          <div className="flex items-center gap-2">
            {/* Filter buttons */}
            <div className="flex items-center gap-1 p-1 bg-muted rounded-lg">
              <Button 
                variant={filter === 'all' ? 'secondary' : 'ghost'} 
                size="sm"
                onClick={() => setFilter('all')}
              >
                All
              </Button>
              {assetClasses.map((assetClass) => {
                const config = ASSET_CLASS_CONFIG[assetClass]
                return (
                  <Button
                    key={assetClass}
                    variant={filter === assetClass ? 'secondary' : 'ghost'}
                    size="sm"
                    onClick={() => setFilter(assetClass)}
                    className="gap-1"
                  >
                    <span>{config.icon}</span>
                    <span className="hidden sm:inline">{config.label}</span>
                  </Button>
                )
              })}
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {filteredPositions.map((position, index) => (
            <PositionRow key={`${position.asset.symbol}-${index}`} position={position} />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Skeleton loader for portfolio summary stats
 */
function PortfolioSummarySkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-4">
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
 * Skeleton loader for allocation chart
 */
function AllocationChartSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-32" />
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="flex items-center justify-center">
            <Skeleton className="h-48 w-48 rounded-full" />
          </div>
          <div className="space-y-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="flex items-center gap-3">
                <Skeleton className="h-4 w-4 rounded" />
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-2 w-full rounded" />
                <Skeleton className="h-4 w-16" />
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Skeleton loader for holdings list
 */
function HoldingsListSkeleton() {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <Skeleton className="h-5 w-24" />
          <div className="flex items-center gap-1">
            <Skeleton className="h-8 w-12" />
            <Skeleton className="h-8 w-16" />
            <Skeleton className="h-8 w-16" />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="flex items-center justify-between py-3 border-b">
              <div className="flex items-center gap-3">
                <Skeleton className="h-10 w-10 rounded-lg" />
                <div>
                  <Skeleton className="h-4 w-24 mb-1" />
                  <Skeleton className="h-3 w-16" />
                </div>
              </div>
              <Skeleton className="h-4 w-16" />
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-4 w-16" />
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
function PortfolioError({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <Card className="py-12 border-red-500/50">
      <CardContent className="text-center">
        <div className="h-16 w-16 rounded-full bg-red-500/10 mx-auto flex items-center justify-center mb-4">
          <AlertCircle className="h-8 w-8 text-red-500" />
        </div>
        <h3 className="text-lg font-semibold mb-2">Failed to Load Portfolio</h3>
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
 * Portfolio Page Component
 * 
 * Displays portfolio positions with loading, error, and empty states.
 * Uses usePortfolio hook for data fetching. Demo mode requires explicit user opt-in
 * to prevent masking real API failures.
 */
export default function PortfolioPage() {
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [useDemoMode, setUseDemoMode] = useState(false)
  const { data, isLoading, error, refetch } = usePortfolio()
  
  // Use real data if available, demo data only if explicitly enabled
  const hasRealData = data !== null && data.positions && data.positions.length > 0
  const positions = hasRealData ? data.positions : (useDemoMode ? mockPortfolioPositions : [])
  const isApiAvailable = hasRealData
  const showEmptyState = !isLoading && !hasRealData && !useDemoMode && !error
  
  const allocations = useMemo(() => calculateAllocations(positions), [positions])

  // Exit demo mode when real data becomes available
  React.useEffect(() => {
    if (hasRealData && useDemoMode) {
      setUseDemoMode(false)
    }
  }, [hasRealData, useDemoMode])

  const handleRefresh = async () => {
    setIsRefreshing(true)
    await refetch()
    setIsRefreshing(false)
  }

  return (
    <ProtectedRoute>
      <AppShell>
        <PageErrorBoundary pageName="Portfolio">
          <div className="space-y-6">
            {/* Page Header */}
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-3xl font-bold tracking-tight">Portfolio</h1>
                <p className="text-muted-foreground">
                  Overview of your holdings across all asset classes
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button 
                  variant="outline" 
                  className="gap-2"
                  onClick={handleRefresh}
                  disabled={isRefreshing || isLoading}
                >
                  <RefreshCw className={cn('h-4 w-4', (isRefreshing || isLoading) && 'animate-spin')} />
                  Refresh
                </Button>
              </div>
            </div>

            {/* API Unavailable Warning - Requires explicit demo mode opt-in */}
            {SHOW_API_WARNING && useDemoMode && !isLoading && (
              <Card className="border-amber-500/50 bg-amber-500/5">
                <CardContent className="py-3">
                  <div className="flex items-center gap-3">
                    <div className="h-8 w-8 rounded-full bg-amber-500/10 flex items-center justify-center shrink-0">
                      <AlertCircle className="h-4 w-4 text-amber-500" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium text-amber-500">Demo Mode Active</p>
                      <p className="text-xs text-muted-foreground">
                        Showing sample data. This is not your real portfolio.
                      </p>
                    </div>
                    <Button 
                      variant="outline" 
                      size="sm" 
                      onClick={() => {
                        setUseDemoMode(false)
                        refetch()
                      }} 
                      className="shrink-0"
                    >
                      Exit Demo Mode
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* No Data State - Prompt to enable demo mode */}
            {showEmptyState && (
              <Card className="border-muted">
                <CardContent className="py-12">
                  <div className="flex flex-col items-center justify-center text-center space-y-4">
                    <div className="h-16 w-16 rounded-full bg-muted flex items-center justify-center">
                      <Wallet className="h-8 w-8 text-muted-foreground" />
                    </div>
                    <div className="space-y-2">
                      <h3 className="text-lg font-semibold">No Portfolio Data</h3>
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
                        <Briefcase className="h-4 w-4 mr-2" />
                        Use Demo Data
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Loading State */}
            {isLoading && (
              <>
              <PortfolioSummarySkeleton />
              <AllocationChartSkeleton />
              <HoldingsListSkeleton />
            </>
          )}

          {/* Error State */}
          {error && !isLoading && (
            <PortfolioError error={error.message} onRetry={refetch} />
          )}

          {/* Content (shown only when we have data - real or demo) */}
          {!isLoading && !showEmptyState && positions.length > 0 && (
            <>
              {/* Summary Stats */}
              <SectionErrorBoundary sectionName="Portfolio Summary">
                <PortfolioSummary positions={positions} />
              </SectionErrorBoundary>

              {/* Allocation Chart */}
              <SectionErrorBoundary sectionName="Asset Allocation Chart">
                <AllocationChart allocations={allocations} />
              </SectionErrorBoundary>

              {/* Holdings List */}
              <SectionErrorBoundary sectionName="Holdings List">
                <HoldingsList positions={positions} />
              </SectionErrorBoundary>
            </>
          )}
        </div>
        </PageErrorBoundary>
      </AppShell>
    </ProtectedRoute>
  )
}
