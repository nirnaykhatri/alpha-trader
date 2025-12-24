/**
 * Positions Page
 * 
 * Detailed view of all open positions with advanced filtering and management.
 * 
 * @module app/positions/page
 */

'use client'

import React, { useState } from 'react'
import { AppShell } from '@/components/layout'
import { ProtectedRoute } from '@/components/auth'
import { 
  Card, 
  CardContent, 
  CardHeader, 
  CardTitle, 
  Badge,
  Button,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui'
import { 
  TrendingUp, 
  TrendingDown, 
  Search,
  Filter,
  X,
  AlertTriangle,
  DollarSign,
  BarChart3,
  Briefcase,
  MoreHorizontal,
} from 'lucide-react'
import { formatCurrency, formatPercent, getPnLTextColor } from '@/lib/utils'

/** Position data structure */
interface Position {
  symbol: string
  quantity: number
  avgCost: number
  currentPrice: number
  marketValue: number
  unrealizedPnL: number
  unrealizedPnLPercent: number
  dayPnL: number
  dayPnLPercent: number
  side: 'long' | 'short'
  openDate: string
  dcaLayers: number
  riskScore: 'low' | 'medium' | 'high'
}

/** Mock positions data */
const mockPositions: Position[] = [
  {
    symbol: 'AAPL',
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
  },
  {
    symbol: 'NVDA',
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
  },
  {
    symbol: 'TSLA',
    quantity: 30,
    avgCost: 245.00,
    currentPrice: 238.75,
    marketValue: 7162.50,
    unrealizedPnL: -187.50,
    unrealizedPnLPercent: -2.55,
    dayPnL: -78.90,
    dayPnLPercent: -1.09,
    side: 'long',
    openDate: '2024-03-12',
    dcaLayers: 4,
    riskScore: 'high',
  },
  {
    symbol: 'MSFT',
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
  },
  {
    symbol: 'AMD',
    quantity: 100,
    avgCost: 165.00,
    currentPrice: 172.35,
    marketValue: 17235.00,
    unrealizedPnL: 735.00,
    unrealizedPnLPercent: 4.45,
    dayPnL: 245.00,
    dayPnLPercent: 1.44,
    side: 'long',
    openDate: '2024-03-01',
    dcaLayers: 2,
    riskScore: 'low',
  },
]

/**
 * ClosePositionDialog Component
 */
function ClosePositionDialog({ position }: { position: Position }) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="danger" size="sm">Close Position</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Close Position: {position.symbol}</DialogTitle>
          <DialogDescription>
            This will close your entire position in {position.symbol}.
          </DialogDescription>
        </DialogHeader>
        <div className="py-4 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">Quantity</p>
              <p className="font-medium">{position.quantity} shares</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Current Price</p>
              <p className="font-medium">{formatCurrency(position.currentPrice)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Market Value</p>
              <p className="font-medium">{formatCurrency(position.marketValue)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Unrealized P&L</p>
              <p className={`font-medium ${getPnLTextColor(position.unrealizedPnL)}`}>
                {formatCurrency(position.unrealizedPnL)}
              </p>
            </div>
          </div>
          <div className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
            <div className="flex items-center gap-2 text-yellow-500">
              <AlertTriangle className="h-4 w-4" />
              <span className="text-sm font-medium">Market Order Warning</span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              This will execute a market order to close your position immediately.
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline">Cancel</Button>
          <Button variant="danger">Close Position</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * PositionCard Component
 * 
 * Displays detailed position information in a card format.
 */
function PositionCard({ position }: { position: Position }) {
  const isProfitable = position.unrealizedPnL >= 0
  const isDayProfitable = position.dayPnL >= 0

  const riskColors = {
    low: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
    medium: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
    high: 'bg-red-500/10 text-red-500 border-red-500/20',
  }

  return (
    <Card className="hover:border-primary/50 transition-colors">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-primary/20 to-primary/5 flex items-center justify-center">
              <span className="font-bold text-sm">{position.symbol[0]}</span>
            </div>
            <div>
              <CardTitle className="text-lg">{position.symbol}</CardTitle>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-xs">
                  {position.side.toUpperCase()}
                </Badge>
                <Badge className={`${riskColors[position.riskScore]} text-xs`} variant="outline">
                  {position.riskScore} risk
                </Badge>
              </div>
            </div>
          </div>
          <Button variant="ghost" size="sm">
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Price and P&L */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-muted-foreground">Current Price</p>
            <p className="text-xl font-bold">{formatCurrency(position.currentPrice)}</p>
          </div>
          <div className="text-right">
            <p className="text-xs text-muted-foreground">Unrealized P&L</p>
            <p className={`text-xl font-bold ${getPnLTextColor(position.unrealizedPnL)}`}>
              {formatCurrency(position.unrealizedPnL)}
            </p>
            <p className={`text-xs ${getPnLTextColor(position.unrealizedPnL)}`}>
              {formatPercent(position.unrealizedPnLPercent)}
            </p>
          </div>
        </div>

        {/* Position Details */}
        <div className="grid grid-cols-3 gap-2 text-sm">
          <div>
            <p className="text-xs text-muted-foreground">Quantity</p>
            <p className="font-medium">{position.quantity}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Avg Cost</p>
            <p className="font-medium">{formatCurrency(position.avgCost)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Market Value</p>
            <p className="font-medium">{formatCurrency(position.marketValue)}</p>
          </div>
        </div>

        {/* Day P&L and DCA Layers */}
        <div className="flex items-center justify-between pt-2 border-t border-border">
          <div>
            <p className="text-xs text-muted-foreground">Day P&L</p>
            <p className={`font-medium ${getPnLTextColor(position.dayPnL)}`}>
              {formatCurrency(position.dayPnL)} ({formatPercent(position.dayPnLPercent)})
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-muted-foreground">DCA Layers</p>
            <div className="flex gap-1">
              {[1, 2, 3, 4, 5].map((layer) => (
                <div
                  key={layer}
                  className={`w-3 h-3 rounded-sm ${
                    layer <= position.dcaLayers ? 'bg-primary' : 'bg-muted'
                  }`}
                />
              ))}
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2 pt-2">
          <Button variant="outline" size="sm" className="flex-1">
            Add to Position
          </Button>
          <ClosePositionDialog position={position} />
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Summary Stats Component
 */
function SummaryStats() {
  const totalValue = mockPositions.reduce((sum, p) => sum + p.marketValue, 0)
  const totalPnL = mockPositions.reduce((sum, p) => sum + p.unrealizedPnL, 0)
  const totalDayPnL = mockPositions.reduce((sum, p) => sum + p.dayPnL, 0)

  return (
    <div className="grid gap-4 md:grid-cols-4">
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Total Positions</p>
              <p className="text-2xl font-bold">{mockPositions.length}</p>
            </div>
            <Briefcase className="h-8 w-8 text-muted-foreground/50" />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Total Value</p>
              <p className="text-2xl font-bold">{formatCurrency(totalValue)}</p>
            </div>
            <DollarSign className="h-8 w-8 text-muted-foreground/50" />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Unrealized P&L</p>
              <p className={`text-2xl font-bold ${getPnLTextColor(totalPnL)}`}>
                {formatCurrency(totalPnL)}
              </p>
            </div>
            {totalPnL >= 0 ? (
              <TrendingUp className="h-8 w-8 text-emerald-500/50" />
            ) : (
              <TrendingDown className="h-8 w-8 text-red-500/50" />
            )}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Day P&L</p>
              <p className={`text-2xl font-bold ${getPnLTextColor(totalDayPnL)}`}>
                {formatCurrency(totalDayPnL)}
              </p>
            </div>
            <BarChart3 className="h-8 w-8 text-muted-foreground/50" />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * Positions Page Component
 */
export default function PositionsPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [filterPnL, setFilterPnL] = useState<string>('all')
  const [filterRisk, setFilterRisk] = useState<string>('all')

  // Filter positions
  const filteredPositions = mockPositions.filter((position) => {
    const matchesSearch = position.symbol.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesPnL = filterPnL === 'all' || 
      (filterPnL === 'profit' && position.unrealizedPnL >= 0) ||
      (filterPnL === 'loss' && position.unrealizedPnL < 0)
    const matchesRisk = filterRisk === 'all' || position.riskScore === filterRisk
    return matchesSearch && matchesPnL && matchesRisk
  })

  const clearFilters = () => {
    setSearchQuery('')
    setFilterPnL('all')
    setFilterRisk('all')
  }

  const hasActiveFilters = searchQuery || filterPnL !== 'all' || filterRisk !== 'all'

  return (
    <ProtectedRoute>
      <AppShell>
        <div className="space-y-6">
          {/* Page Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">Positions</h1>
              <p className="text-muted-foreground">
                Manage and monitor all your open positions
              </p>
            </div>
            <Button className="gap-2">
              <TrendingUp className="h-4 w-4" />
              New Position
            </Button>
          </div>

          {/* Summary Stats */}
          <SummaryStats />

          {/* Filters */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex flex-wrap items-center gap-4">
                <div className="relative flex-1 min-w-[200px]">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search by symbol..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9"
                  />
                </div>
                <Select value={filterPnL} onValueChange={setFilterPnL}>
                  <SelectTrigger className="w-[150px]">
                    <Filter className="h-4 w-4 mr-2" />
                    <SelectValue placeholder="P&L" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All P&L</SelectItem>
                    <SelectItem value="profit">Profitable</SelectItem>
                    <SelectItem value="loss">At Loss</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={filterRisk} onValueChange={setFilterRisk}>
                  <SelectTrigger className="w-[150px]">
                    <AlertTriangle className="h-4 w-4 mr-2" />
                    <SelectValue placeholder="Risk" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Risk</SelectItem>
                    <SelectItem value="low">Low Risk</SelectItem>
                    <SelectItem value="medium">Medium Risk</SelectItem>
                    <SelectItem value="high">High Risk</SelectItem>
                  </SelectContent>
                </Select>
                {hasActiveFilters && (
                  <Button variant="ghost" size="sm" onClick={clearFilters} className="gap-1">
                    <X className="h-4 w-4" />
                    Clear
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Positions Grid */}
          {filteredPositions.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {filteredPositions.map((position) => (
                <PositionCard key={position.symbol} position={position} />
              ))}
            </div>
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                <Search className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                <p className="text-lg font-medium">No positions found</p>
                <p className="text-muted-foreground">
                  {hasActiveFilters 
                    ? 'Try adjusting your filters'
                    : 'Open a new position to get started'}
                </p>
                {hasActiveFilters && (
                  <Button variant="outline" className="mt-4" onClick={clearFilters}>
                    Clear Filters
                  </Button>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </AppShell>
    </ProtectedRoute>
  )
}
