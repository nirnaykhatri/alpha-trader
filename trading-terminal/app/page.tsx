'use client'

import { useEffect, useState } from 'react'
import { TrendingUp, TrendingDown, RefreshCw, Activity, DollarSign, BarChart3, Target, AlertTriangle } from 'lucide-react'
import { AppShell } from '@/components/layout'
import { ProtectedRoute } from '@/components/auth'
import { PositionCard } from '@/components/position-card'
import { StatsCard } from '@/components/stats-card'
import { Card, CardContent, CardHeader, CardTitle, Badge } from '@/components/ui'
import { SectionErrorBoundary } from '@/components/error-boundary'
import { useTrading } from '@/lib/hooks/use-trading'
import { useSignalR } from '@/lib/hooks/use-signalr'
import { formatCurrency, formatPercent, formatRelativeTime, getPnLTextColor } from '@/lib/utils'

export default function Dashboard() {
  const { positions, portfolio, isLoading, error, refresh } = useTrading()
  const { isConnected, lastUpdate, botStatus } = useSignalR()
  const [isRefreshing, setIsRefreshing] = useState(false)

  const handleRefresh = async () => {
    setIsRefreshing(true)
    await refresh()
    setIsRefreshing(false)
  }

  // Calculate aggregate stats
  const totalUnrealizedPnL = positions?.reduce((sum, p) => sum + (p.unrealized_pnl || 0), 0) || 0
  const totalPositions = positions?.length || 0
  const profitablePositions = positions?.filter(p => (p.unrealized_pnl || 0) > 0).length || 0
  const portfolioEquity = portfolio?.equity || 0
  const buyingPower = portfolio?.buying_power || 0

  return (
    <ProtectedRoute>
      <AppShell>
        <div className="space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
              <p className="text-muted-foreground">
                Real-time monitoring of your trading positions
              </p>
            </div>
            <div className="flex items-center gap-4">
              {/* Connection Status */}
              <Badge variant={isConnected ? 'success' : 'destructive'} className="gap-1">
                <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-100' : 'bg-red-100'}`} />
                {isConnected ? 'Live' : 'Disconnected'}
              </Badge>
              
              {/* Refresh Button */}
              <button
                onClick={handleRefresh}
                disabled={isRefreshing}
                className="flex items-center gap-2 px-4 py-2 rounded-md bg-secondary hover:bg-secondary/80 transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>
          </div>

          {/* Stats Overview */}
          <SectionErrorBoundary sectionName="Stats Overview" compact>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Total P&L
                </CardTitle>
                <DollarSign className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className={`text-2xl font-bold ${getPnLTextColor(totalUnrealizedPnL)}`}>
                  {formatCurrency(totalUnrealizedPnL)}
                </div>
                <p className="text-xs text-muted-foreground">
                  Unrealized
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Active Positions
                </CardTitle>
                <Activity className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{totalPositions}</div>
                <p className="text-xs text-muted-foreground">
                  Open trades
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Win Rate
                </CardTitle>
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {totalPositions > 0 ? `${profitablePositions}/${totalPositions}` : '0/0'}
                </div>
                <p className="text-xs text-emerald-500">
                  {totalPositions > 0 
                    ? formatPercent(profitablePositions / totalPositions * 100) + ' profitable'
                    : 'No positions'
                  }
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Portfolio Value
                </CardTitle>
                <BarChart3 className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{formatCurrency(portfolioEquity)}</div>
                <p className="text-xs text-muted-foreground">
                  {buyingPower ? `${formatCurrency(buyingPower)} buying power` : 'Loading...'}
                </p>
              </CardContent>
            </Card>
          </div>
          </SectionErrorBoundary>

          {/* Quick Stats Row */}
          <SectionErrorBoundary sectionName="Quick Stats" compact>
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Target className="h-4 w-4" />
                  Day's Performance
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className={`text-2xl font-bold ${getPnLTextColor(totalUnrealizedPnL)}`}>
                  {formatCurrency(totalUnrealizedPnL)}
                </div>
                <div className="mt-2 h-2 bg-muted rounded-full overflow-hidden">
                  <div 
                    className={`h-full rounded-full ${totalUnrealizedPnL >= 0 ? 'bg-emerald-500' : 'bg-red-500'}`} 
                    style={{ width: `${Math.min(Math.abs(totalUnrealizedPnL) / (portfolioEquity || 1) * 100, 100)}%` }} 
                  />
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {portfolioEquity > 0 
                    ? formatPercent(totalUnrealizedPnL / portfolioEquity * 100) + ' today'
                    : 'No data'
                  }
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Activity className="h-4 w-4" />
                  Bot Status
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-2">
                  <Badge variant={botStatus.isRunning ? 'success' : 'secondary'}>
                    {botStatus.isRunning ? 'Running' : 'Stopped'}
                  </Badge>
                  <span className="text-sm text-muted-foreground">
                    {botStatus.strategyName} {botStatus.isRunning ? 'Active' : 'Idle'}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  {botStatus.tradesToday} trade{botStatus.tradesToday !== 1 ? 's' : ''} today
                  {botStatus.lastSignalTime 
                    ? ` • Last signal ${formatRelativeTime(botStatus.lastSignalTime)}`
                    : ' • No signals yet'
                  }
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4" />
                  Risk Status
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-2">
                  <Badge variant="success">Low Risk</Badge>
                </div>
                <div className="mt-2 flex gap-1">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <div 
                      key={i}
                      className={`h-2 flex-1 rounded ${i <= 2 ? 'bg-emerald-500' : 'bg-muted'}`}
                    />
                  ))}
                </div>
                <p className="text-xs text-muted-foreground mt-1">All positions within limits</p>
              </CardContent>
            </Card>
          </div>
          </SectionErrorBoundary>

          {/* Positions Grid */}
          <SectionErrorBoundary sectionName="Positions Grid">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Open Positions</CardTitle>
                {lastUpdate && (
                  <span className="text-sm text-muted-foreground">
                    Last update: {lastUpdate.toLocaleTimeString()}
                  </span>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="p-4 rounded-lg border bg-muted/50 animate-pulse">
                      <div className="h-6 bg-muted rounded w-1/3 mb-4" />
                      <div className="space-y-2">
                        <div className="h-4 bg-muted rounded w-full" />
                        <div className="h-4 bg-muted rounded w-2/3" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : error ? (
                <div className="text-center py-12">
                  <p className="text-destructive mb-4">{error}</p>
                  <button
                    onClick={handleRefresh}
                    className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90"
                  >
                    Try Again
                  </button>
                </div>
              ) : positions && positions.length > 0 ? (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {positions.map((position) => (
                    <PositionCard key={position.symbol} position={position} />
                  ))}
                </div>
              ) : (
                <div className="text-center py-12 border rounded-lg bg-muted/50">
                  <Activity className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
                  <p className="text-lg font-medium">No Open Positions</p>
                  <p className="text-muted-foreground">
                    Positions will appear here when trades are executed
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
          </SectionErrorBoundary>
        </div>
      </AppShell>
    </ProtectedRoute>
  )
}
