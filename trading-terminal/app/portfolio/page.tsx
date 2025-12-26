/**
 * Portfolio Page
 * 
 * Comprehensive portfolio overview with asset allocation, distribution charts,
 * and multi-asset class support (stocks, forex, crypto, commodities).
 * 
 * @module app/portfolio/page
 */

'use client'

import React, { useState, useMemo, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/layout'
import { ProtectedRoute } from '@/components/auth'
import { PageErrorBoundary, SectionErrorBoundary } from '@/components/error-boundary'
import { Card, CardContent, CardHeader, CardTitle, Badge, Button, Skeleton, useToast } from '@/components/ui'
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
  ExternalLink,
  XCircle,
  Eye,
  Layers,
  Building2,
} from 'lucide-react'
import { formatCurrency, formatPercent, formatAssetPrice, cn, getPnLTextColor } from '@/lib/utils'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui'
import {
  AssetClass,
  AssetPosition,
  AssetAllocation,
  ASSET_CLASS_CONFIG,
  createAssetFromSymbol,
  getDisplaySymbol,
} from '@/lib/types/asset'
import { usePortfolio } from '@/lib/hooks'
import { closePosition as adminClosePosition } from '@/lib/admin-api'

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
    broker: 'alpaca',
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
    broker: 'alpaca',
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
    broker: 'tastytrade',
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
    broker: 'coinbase',
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
    broker: 'coinbase',
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
    broker: 'ibkr',
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
    broker: 'ibkr',
  },
  // Another AAPL position at different broker (to demonstrate consolidated view)
  {
    asset: createAssetFromSymbol('AAPL', 'Apple Inc.'),
    quantity: 30,
    avgCost: 175.00,
    currentPrice: 182.45,
    marketValue: 5473.50,
    unrealizedPnL: 223.50,
    unrealizedPnLPercent: 4.26,
    dayPnL: 27.14,
    dayPnLPercent: 0.50,
    side: 'long',
    openDate: '2024-03-15',
    dcaLayers: 1,
    riskScore: 'low',
    portfolioWeight: 7.5,
    broker: 'tastytrade',
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

/** Format broker name for display */
function formatBrokerName(broker: string): string {
  const brokerNames: Record<string, string> = {
    'alpaca': 'Alpaca',
    'tastytrade': 'TastyTrade',
    'ibkr': 'Interactive Brokers',
    'schwab': 'Schwab',
    'fidelity': 'Fidelity',
    'coinbase': 'Coinbase',
    'binance': 'Binance',
  }
  return brokerNames[broker.toLowerCase()] || broker.charAt(0).toUpperCase() + broker.slice(1)
}

/** Get broker badge color */
function getBrokerColor(broker: string): string {
  const brokerColors: Record<string, string> = {
    'alpaca': 'bg-yellow-500/10 text-yellow-500 border-yellow-500/30',
    'tastytrade': 'bg-red-500/10 text-red-500 border-red-500/30',
    'ibkr': 'bg-red-600/10 text-red-600 border-red-600/30',
    'schwab': 'bg-blue-500/10 text-blue-500 border-blue-500/30',
    'coinbase': 'bg-blue-600/10 text-blue-600 border-blue-600/30',
    'binance': 'bg-amber-500/10 text-amber-500 border-amber-500/30',
  }
  return brokerColors[broker.toLowerCase()] || 'bg-slate-500/10 text-slate-400 border-slate-500/30'
}

/** Get broker external URL for position */
function getBrokerUrl(broker: string, symbol: string): string {
  const brokerUrls: Record<string, string> = {
    'alpaca': `https://app.alpaca.markets/paper/dashboard/overview`,
    'tastytrade': `https://trade.tastyworks.com/`,
    'ibkr': `https://www.interactivebrokers.com/portal/`,
    'schwab': `https://client.schwab.com/`,
    'fidelity': `https://digital.fidelity.com/prgw/digital/`,
    'coinbase': `https://www.coinbase.com/advanced-trade/spot/${symbol}-USD`,
    'binance': `https://www.binance.com/en/trade/${symbol}_USDT`,
  }
  return brokerUrls[broker.toLowerCase()] || '#'
}

/**
 * Position Details Dialog
 */
function PositionDetailsDialog({ 
  position, 
  open, 
  onOpenChange 
}: { 
  position: AssetPosition
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const config = ASSET_CLASS_CONFIG[position.asset.assetClass]
  const brokerName = formatBrokerName(position.broker || 'Unknown')
  const costBasis = position.avgCost * position.quantity
  
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <div className={cn('w-8 h-8 rounded-lg flex items-center justify-center text-base', config.bgColor)}>
              {config.icon}
            </div>
            {getDisplaySymbol(position.asset)} Position
          </DialogTitle>
          <DialogDescription>
            {position.asset.name} @ {brokerName}
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4">
          {/* Position Summary */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">Side</p>
              <Badge variant="outline">{position.side.toUpperCase()}</Badge>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">Asset Class</p>
              <Badge variant="secondary" className={config.color}>{config.label}</Badge>
            </div>
          </div>
          
          {/* Position Details */}
          <div className="rounded-lg border p-4 space-y-3">
            <div className="flex justify-between">
              <span className="text-sm text-muted-foreground">Quantity</span>
              <span className="font-medium">{position.quantity}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-muted-foreground">Avg Cost</span>
              <span className="font-medium">{formatCurrency(position.avgCost)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-muted-foreground">Current Price</span>
              <span className={cn('font-medium', getPnLTextColor(position.unrealizedPnL))}>
                {formatCurrency(position.currentPrice)}
              </span>
            </div>
            <div className="border-t pt-3 flex justify-between">
              <span className="text-sm text-muted-foreground">Cost Basis</span>
              <span className="font-medium">{formatCurrency(costBasis)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-muted-foreground">Market Value</span>
              <span className="font-bold">{formatCurrency(position.marketValue)}</span>
            </div>
          </div>
          
          {/* P&L Summary */}
          <div className="rounded-lg border p-4 space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Unrealized P&L</span>
              <div className="text-right">
                <span className={cn('font-bold', getPnLTextColor(position.unrealizedPnL))}>
                  {formatCurrency(position.unrealizedPnL)}
                </span>
                <span className={cn('text-xs ml-2', getPnLTextColor(position.unrealizedPnL))}>
                  ({formatPercent(position.unrealizedPnLPercent)})
                </span>
              </div>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Day P&L</span>
              <div className="text-right">
                <span className={cn('font-medium', getPnLTextColor(position.dayPnL))}>
                  {formatCurrency(position.dayPnL)}
                </span>
                <span className={cn('text-xs ml-2', getPnLTextColor(position.dayPnL))}>
                  ({formatPercent(position.dayPnLPercent)})
                </span>
              </div>
            </div>
          </div>
          
          {/* Additional Info */}
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground">Open Date</p>
              <p className="font-medium">{position.openDate}</p>
            </div>
            <div>
              <p className="text-muted-foreground">DCA Layers</p>
              <p className="font-medium">{position.dcaLayers}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Risk Score</p>
              <Badge variant={
                position.riskScore === 'low' ? 'success' : 
                position.riskScore === 'medium' ? 'warning' : 'danger'
              }>
                {position.riskScore.toUpperCase()}
              </Badge>
            </div>
            <div>
              <p className="text-muted-foreground">Portfolio Weight</p>
              <p className="font-medium">{formatPercent(position.portfolioWeight)}</p>
            </div>
          </div>
        </div>
        
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Close Position Confirmation Dialog
 */
function ClosePositionDialog({
  position,
  open,
  onOpenChange,
  onConfirm,
  isClosing,
}: {
  position: AssetPosition
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
  isClosing: boolean
}) {
  const brokerName = formatBrokerName(position.broker || 'Unknown')
  
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Close {getDisplaySymbol(position.asset)} Position?</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-3">
              <p>
                This will sell your entire position of <strong>{position.quantity}</strong> shares 
                of <strong>{getDisplaySymbol(position.asset)}</strong> at {brokerName}.
              </p>
              <div className="rounded-lg bg-muted p-3 space-y-2">
                <div className="flex justify-between text-sm">
                  <span>Current Price</span>
                  <span className="font-medium">{formatCurrency(position.currentPrice)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span>Est. Proceeds</span>
                  <span className="font-medium">{formatCurrency(position.marketValue)}</span>
                </div>
                <div className="flex justify-between text-sm border-t pt-2">
                  <span>Unrealized P&L</span>
                  <span className={cn('font-bold', getPnLTextColor(position.unrealizedPnL))}>
                    {formatCurrency(position.unrealizedPnL)} ({formatPercent(position.unrealizedPnLPercent)})
                  </span>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                This action will place a market order to close the position. 
                Actual fill price may vary.
              </p>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isClosing}>Cancel</AlertDialogCancel>
          <AlertDialogAction 
            onClick={onConfirm}
            disabled={isClosing}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {isClosing ? 'Closing...' : 'Close Position'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

/**
 * Position Row Component
 */
function PositionRow({ position, onRefresh }: { position: AssetPosition; onRefresh?: () => void }) {
  const router = useRouter()
  const { toast } = useToast()
  const [showDetails, setShowDetails] = useState(false)
  const [showCloseConfirm, setShowCloseConfirm] = useState(false)
  const [isClosing, setIsClosing] = useState(false)
  
  const config = ASSET_CLASS_CONFIG[position.asset.assetClass]
  const isProfitable = position.unrealizedPnL >= 0
  const brokerName = formatBrokerName(position.broker || 'Unknown')

  // Handle View Details
  const handleViewDetails = useCallback(() => {
    setShowDetails(true)
  }, [])

  // Handle Add DCA Layer - navigate to new order page with prefilled data
  const handleAddDCA = useCallback(() => {
    const symbol = getDisplaySymbol(position.asset)
    router.push(`/orders/new?symbol=${encodeURIComponent(symbol)}&side=buy&type=dca`)
    toast({
      title: 'Add DCA Layer',
      description: `Creating DCA order for ${symbol}`,
    })
  }, [router, position.asset, toast])

  // Handle Open in Broker - open broker's platform in new tab
  const handleOpenInBroker = useCallback(() => {
    const url = getBrokerUrl(position.broker || '', position.asset.symbol)
    if (url && url !== '#') {
      window.open(url, '_blank', 'noopener,noreferrer')
    } else {
      toast({
        title: 'Unable to open',
        description: `No direct link available for ${brokerName}`,
        variant: 'destructive',
      })
    }
  }, [position.broker, position.asset.symbol, brokerName, toast])

  // Handle Close Position - uses the admin API for authenticated position closing
  const handleClosePosition = useCallback(async () => {
    setIsClosing(true)
    try {
      // Use the admin API closePosition function which calls POST /admin/positions/{symbol}/close
      await adminClosePosition(position.asset.symbol, {
        quantity: position.quantity,
        order_type: 'market',
      })

      toast({
        title: 'Position Closed',
        description: `Successfully closed ${position.quantity} shares of ${getDisplaySymbol(position.asset)}`,
      })
      setShowCloseConfirm(false)
      onRefresh?.()
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to close position',
        variant: 'destructive',
      })
    } finally {
      setIsClosing(false)
    }
  }, [position, toast, onRefresh])

  return (
    <>
      <div className="flex items-center justify-between p-4 hover:bg-muted/50 rounded-lg transition-colors">
        <div className="flex items-center gap-4">
          {/* Asset Icon/Logo */}
          <div className={cn('w-10 h-10 rounded-lg flex items-center justify-center text-lg', config.bgColor)}>
            {config.icon}
          </div>
          
          {/* Asset Info */}
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold">{getDisplaySymbol(position.asset)}</span>
              <Badge variant="outline" className="text-xs">
                {position.side.toUpperCase()}
              </Badge>
              <Badge variant="secondary" className={cn('text-xs', config.color)}>
                {config.label}
              </Badge>
              {/* Broker Badge */}
              {position.broker && (
                <Badge 
                  variant="outline" 
                  className={cn('text-xs gap-1', getBrokerColor(position.broker))}
                >
                  <Building2 className="h-3 w-3" />
                  {brokerName}
                </Badge>
              )}
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

        {/* Actions Dropdown */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="ml-4">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuLabel className="text-xs text-muted-foreground">
              {getDisplaySymbol(position.asset)} @ {brokerName}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="gap-2 cursor-pointer" onClick={handleViewDetails}>
              <Eye className="h-4 w-4" />
              View Details
            </DropdownMenuItem>
            <DropdownMenuItem className="gap-2 cursor-pointer" onClick={handleAddDCA}>
              <Layers className="h-4 w-4" />
              Add DCA Layer
            </DropdownMenuItem>
            <DropdownMenuItem className="gap-2 cursor-pointer" onClick={handleOpenInBroker}>
              <ExternalLink className="h-4 w-4" />
              Open in {brokerName}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem 
              className="gap-2 cursor-pointer text-loss focus:text-loss"
              onClick={() => setShowCloseConfirm(true)}
            >
              <XCircle className="h-4 w-4" />
              Close Position
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      
      {/* Position Details Dialog */}
      <PositionDetailsDialog 
        position={position} 
        open={showDetails} 
        onOpenChange={setShowDetails} 
      />
      
      {/* Close Position Confirmation Dialog */}
      <ClosePositionDialog
        position={position}
        open={showCloseConfirm}
        onOpenChange={setShowCloseConfirm}
        onConfirm={handleClosePosition}
        isClosing={isClosing}
      />
    </>
  )
}

/** View mode for holdings list */
type ViewMode = 'by-broker' | 'consolidated'

/** Consolidated position (aggregated across brokers) */
interface ConsolidatedPosition {
  symbol: string
  positions: AssetPosition[]
  totalQuantity: number
  totalMarketValue: number
  totalUnrealizedPnL: number
  avgCost: number
  currentPrice: number
  pnlPercent: number
}

/**
 * Consolidated Position Row Component
 * Shows aggregated position across multiple brokers with expandable details
 */
function ConsolidatedPositionRow({ consolidated }: { consolidated: ConsolidatedPosition }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const firstPosition = consolidated.positions[0]
  const config = ASSET_CLASS_CONFIG[firstPosition?.asset.assetClass || 'stock']
  const isProfitable = consolidated.totalUnrealizedPnL >= 0
  const hasMuitipleBrokers = consolidated.positions.length > 1
  
  return (
    <div className="rounded-lg border border-border/50">
      {/* Main Row */}
      <div 
        className={cn(
          "flex items-center justify-between p-4 transition-colors",
          hasMuitipleBrokers && "cursor-pointer hover:bg-muted/50"
        )}
        onClick={() => hasMuitipleBrokers && setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-4">
          {/* Asset Icon/Logo */}
          <div className={cn('w-10 h-10 rounded-lg flex items-center justify-center text-lg', config.bgColor)}>
            {config.icon}
          </div>
          
          {/* Asset Info */}
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold">{consolidated.symbol}</span>
              <Badge variant="secondary" className={cn('text-xs', config.color)}>
                {config.label}
              </Badge>
              {hasMuitipleBrokers && (
                <Badge variant="outline" className="text-xs gap-1">
                  <Building2 className="h-3 w-3" />
                  {consolidated.positions.length} brokers
                </Badge>
              )}
              {!hasMuitipleBrokers && consolidated.positions[0]?.broker && (
                <Badge 
                  variant="outline" 
                  className={cn('text-xs gap-1', getBrokerColor(consolidated.positions[0].broker))}
                >
                  <Building2 className="h-3 w-3" />
                  {formatBrokerName(consolidated.positions[0].broker)}
                </Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground">{firstPosition?.asset.name}</p>
          </div>
        </div>

        {/* Position Details */}
        <div className="hidden md:flex items-center gap-8">
          <div className="text-right">
            <p className="text-sm text-muted-foreground">Total Qty</p>
            <p className="font-medium">{consolidated.totalQuantity}</p>
          </div>
          <div className="text-right">
            <p className="text-sm text-muted-foreground">Avg Cost</p>
            <p className="font-medium">{formatCurrency(consolidated.avgCost)}</p>
          </div>
          <div className="text-right">
            <p className="text-sm text-muted-foreground">Current</p>
            <p className={cn('font-medium', getPnLTextColor(consolidated.totalUnrealizedPnL))}>
              {formatCurrency(consolidated.currentPrice)}
            </p>
          </div>
          <div className="text-right">
            <p className="text-sm text-muted-foreground">Market Value</p>
            <p className="font-medium">{formatCurrency(consolidated.totalMarketValue)}</p>
          </div>
        </div>

        {/* P&L */}
        <div className="text-right">
          <p className={cn('font-bold', getPnLTextColor(consolidated.totalUnrealizedPnL))}>
            {formatCurrency(consolidated.totalUnrealizedPnL)}
          </p>
          <p className={cn('text-xs flex items-center justify-end gap-1', 
            getPnLTextColor(consolidated.totalUnrealizedPnL))}>
            {isProfitable ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
            {formatPercent(consolidated.pnlPercent)}
          </p>
        </div>

        {/* Expand Indicator */}
        {hasMuitipleBrokers && (
          <div className="ml-4">
            <ArrowDownRight className={cn(
              "h-4 w-4 transition-transform text-muted-foreground",
              isExpanded && "rotate-[-135deg]"
            )} />
          </div>
        )}
      </div>
      
      {/* Expanded Broker Details */}
      {isExpanded && hasMuitipleBrokers && (
        <div className="border-t border-border/50 bg-muted/30">
          {consolidated.positions.map((position, index) => (
            <div 
              key={`${position.broker}-${index}`}
              className="flex items-center justify-between px-4 py-3 pl-16 border-b last:border-b-0 border-border/30"
            >
              <div className="flex items-center gap-3">
                <Badge 
                  variant="outline" 
                  className={cn('text-xs gap-1', getBrokerColor(position.broker || 'Unknown'))}
                >
                  <Building2 className="h-3 w-3" />
                  {formatBrokerName(position.broker || 'Unknown')}
                </Badge>
                <span className="text-sm text-muted-foreground">
                  {position.quantity} shares @ {formatCurrency(position.avgCost)}
                </span>
              </div>
              <div className="flex items-center gap-6">
                <span className="text-sm">{formatCurrency(position.marketValue)}</span>
                <span className={cn('text-sm font-medium', getPnLTextColor(position.unrealizedPnL))}>
                  {formatCurrency(position.unrealizedPnL)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Holdings List Component
 */
function HoldingsList({ positions, onRefresh }: { positions: AssetPosition[]; onRefresh?: () => void }) {
  const [filter, setFilter] = useState<AssetClass | 'all'>('all')
  const [sortBy, setSortBy] = useState<'value' | 'pnl' | 'change'>('value')
  const [viewMode, setViewMode] = useState<ViewMode>('by-broker')
  
  // Get unique brokers for consolidated view info
  const uniqueBrokers = useMemo(() => {
    return Array.from(new Set(positions.map(p => p.broker || 'Unknown')))
  }, [positions])
  
  // Consolidated positions (grouped by symbol)
  const consolidatedPositions = useMemo((): ConsolidatedPosition[] => {
    const symbolMap = new Map<string, AssetPosition[]>()
    
    positions.forEach(p => {
      const symbol = p.asset.symbol
      const existing = symbolMap.get(symbol) || []
      existing.push(p)
      symbolMap.set(symbol, existing)
    })
    
    return Array.from(symbolMap.entries()).map(([symbol, positionList]) => {
      const totalQuantity = positionList.reduce((sum, p) => sum + p.quantity, 0)
      const totalMarketValue = positionList.reduce((sum, p) => sum + p.marketValue, 0)
      const totalUnrealizedPnL = positionList.reduce((sum, p) => sum + p.unrealizedPnL, 0)
      const totalCost = positionList.reduce((sum, p) => sum + (p.avgCost * p.quantity), 0)
      const avgCost = totalQuantity !== 0 ? totalCost / totalQuantity : 0
      const currentPrice = positionList[0]?.currentPrice || 0
      const pnlPercent = totalCost !== 0 ? (totalUnrealizedPnL / totalCost) * 100 : 0
      
      return {
        symbol,
        positions: positionList,
        totalQuantity,
        totalMarketValue,
        totalUnrealizedPnL,
        avgCost,
        currentPrice,
        pnlPercent,
      }
    })
  }, [positions])

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
        <div className="flex items-center justify-between flex-wrap gap-2">
          <CardTitle className="text-lg flex items-center gap-2">
            <Briefcase className="h-5 w-5" />
            Holdings
            {uniqueBrokers.length > 1 && (
              <Badge variant="outline" className="text-xs ml-2">
                {uniqueBrokers.length} brokers
              </Badge>
            )}
          </CardTitle>
          <div className="flex items-center gap-2 flex-wrap">
            {/* View Mode Toggle (only show when multiple brokers) */}
            {uniqueBrokers.length > 1 && (
              <div className="flex items-center gap-1 p-1 bg-muted rounded-lg">
                <Button 
                  variant={viewMode === 'by-broker' ? 'secondary' : 'ghost'} 
                  size="sm"
                  onClick={() => setViewMode('by-broker')}
                  className="gap-1"
                >
                  <Building2 className="h-3 w-3" />
                  <span className="hidden sm:inline">By Broker</span>
                </Button>
                <Button 
                  variant={viewMode === 'consolidated' ? 'secondary' : 'ghost'} 
                  size="sm"
                  onClick={() => setViewMode('consolidated')}
                  className="gap-1"
                >
                  <Layers className="h-3 w-3" />
                  <span className="hidden sm:inline">Consolidated</span>
                </Button>
              </div>
            )}
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
        {viewMode === 'by-broker' ? (
          <div className="space-y-2">
            {filteredPositions.map((position, index) => (
              <PositionRow 
                key={`${position.asset.symbol}-${position.broker}-${index}`} 
                position={position}
                onRefresh={onRefresh}
              />
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {consolidatedPositions
              .filter(cp => filter === 'all' || cp.positions[0]?.asset.assetClass === filter)
              .sort((a, b) => b.totalMarketValue - a.totalMarketValue)
              .map((consolidated) => (
                <ConsolidatedPositionRow 
                  key={consolidated.symbol} 
                  consolidated={consolidated} 
                />
              ))}
          </div>
        )}
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
  
  // Transform API positions (flat structure) to AssetPosition type (nested asset object)
  // Backend returns: { symbol, assetClass, ... }
  // Frontend expects: { asset: { symbol, assetClass, ... }, quantity, ... }
  const transformedPositions = useMemo((): AssetPosition[] => {
    if (!data?.positions || data.positions.length === 0) return []
    
    return data.positions.map((pos) => ({
      asset: createAssetFromSymbol(
        pos.symbol || 'UNKNOWN',
        pos.name || pos.symbol || 'Unknown',
        { assetClass: pos.assetClass || 'stock' }
      ),
      quantity: pos.quantity || 0,
      avgCost: pos.avgPrice || pos.avgCost || 0,
      currentPrice: pos.currentPrice || 0,
      marketValue: pos.marketValue || 0,
      unrealizedPnL: pos.unrealizedPnL || 0,
      unrealizedPnLPercent: pos.unrealizedPnLPercent || 0,
      dayPnL: pos.dayPnL || 0,
      dayPnLPercent: pos.dayPnLPercent || 0,
      side: pos.side || 'long',
      openDate: pos.openDate || new Date().toISOString().split('T')[0],
      dcaLayers: pos.dcaLayers || 0,
      riskScore: pos.riskScore || 'medium',
      portfolioWeight: pos.portfolioWeight || 0,
      broker: pos.broker || 'Unknown',
    }))
  }, [data?.positions])
  
  // Use real data if available, demo data only if explicitly enabled
  const hasRealData = transformedPositions.length > 0
  const positions = hasRealData ? transformedPositions : (useDemoMode ? mockPortfolioPositions : [])
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
                <HoldingsList positions={positions} onRefresh={refetch} />
              </SectionErrorBoundary>
            </>
          )}
        </div>
        </PageErrorBoundary>
      </AppShell>
    </ProtectedRoute>
  )
}
