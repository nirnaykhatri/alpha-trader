/**
 * Bots Management Page
 * 
 * Main page for managing trading bots with list view, history, and actions.
 * UI inspired by Bitsgap bot management dashboard.
 * 
 * @module app/bots/page
 */

'use client'

import React, { useState, useMemo, useCallback } from 'react'
import { AppShell } from '@/components/layout'
import { ProtectedRoute } from '@/components/auth'
import { BotConfigDialog, BotOrdersDialog, BotModifyDialog } from '@/components/trading'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Badge,
  Button,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
} from '@/components/ui'
import {
  Plus,
  Search,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Pause,
  Play,
  Square,
  Eye,
  Settings,
  Trash2,
  ChevronRight,
  Bot as BotIcon,
  Activity,
  Clock,
  DollarSign,
  BarChart3,
  History,
  AlertCircle,
  X,
  Download,
} from 'lucide-react'
import { StatsCard } from '@/components/stats-card'
import { EmptyState } from '@/components/empty-state'
import { getPnLTextColor } from '@/lib/utils'
import {
  useBots,
  useBot,
  useBotHistory,
  useBotHistoryStats,
} from '@/lib/hooks/use-admin-api'
import { 
  performBotAction, 
  updateBot as updateBotApi, 
  type BotActionRequest 
} from '@/lib/admin-api'
import { useToast } from '@/components/ui'
import type {
  Bot,
  BotHistoryEntry,
  CreateBotRequest,
  UpdateBotRequest,
} from '@/lib/types/bot'
import {
  BOT_STATE_CONFIG,
  BOT_TYPE_LABELS,
  formatPnL,
  formatPnLPercent,
  formatTradingTime,
  isBotActive,
} from '@/lib/types/bot'

// ============================================================================
// Sub-components
// ============================================================================

/**
 * Bot State Badge
 */
function BotStateBadge({ state }: { state: Bot['state'] }) {
  const config = BOT_STATE_CONFIG[state]
  return (
    <Badge className={`${config.bgColor} ${config.color} border-0`}>
      <span className="mr-1">{config.icon}</span>
      {config.label}
    </Badge>
  )
}

/**
 * PnL Display with color
 */
function PnLDisplay({ value, percent }: { value: number; percent: number }) {
  const isPositive = value >= 0
  const colorClass = getPnLTextColor(value)
  
  return (
    <div className={colorClass}>
      <span className="font-semibold">
        {isPositive ? '+' : ''}{value.toFixed(2)}
      </span>
      <span className="text-xs ml-1">
        ({isPositive ? '+' : ''}{percent.toFixed(2)}%)
      </span>
    </div>
  )
}

/**
 * Single Bot Row in the table
 */
function BotRow({
  bot,
  onSelect,
  isSelected,
}: {
  bot: Bot
  onSelect: (bot: Bot) => void
  isSelected: boolean
}) {
  const perf = bot.performance

  return (
    <div
      onClick={() => onSelect(bot)}
      className={`
        grid grid-cols-[2fr_1fr_1fr_1fr_1fr_1fr_auto] gap-4 items-center p-4 
        border-b hover:bg-muted/50 cursor-pointer transition-colors
        ${isSelected ? 'bg-muted/70 border-l-2 border-l-primary' : ''}
      `}
    >
      {/* Strategy/Bot Info */}
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
          <BotIcon className="h-5 w-5 text-primary" />
        </div>
        <div>
          <div className="font-medium flex items-center gap-2">
            {bot.name}
            <Badge variant="outline" className="text-xs font-normal">
              {BOT_TYPE_LABELS[bot.botType]}
            </Badge>
          </div>
          <div className="text-sm text-muted-foreground">
            {bot.symbol} • {bot.exchange}
          </div>
        </div>
      </div>

      {/* Current Value */}
      <div>
        <div className="font-medium">${perf.currentValue.toFixed(2)}</div>
        <div className="text-xs text-muted-foreground">
          Invested: ${perf.totalInvested.toFixed(2)}
        </div>
      </div>

      {/* Total PnL */}
      <PnLDisplay value={perf.totalPnL} percent={perf.totalPnLPercent} />

      {/* Bot Profit */}
      <PnLDisplay value={perf.botProfit} percent={perf.botProfitPercent} />

      {/* Avg Daily */}
      <div className={getPnLTextColor(perf.avgDailyProfit)}>
        {perf.avgDailyProfit >= 0 ? '+' : ''}{perf.avgDailyProfit.toFixed(2)}%
      </div>

      {/* State */}
      <BotStateBadge state={bot.state} />

      {/* Actions */}
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="icon" className="h-8 w-8">
          <Eye className="h-4 w-4" />
        </Button>
        <ChevronRight className="h-4 w-4 text-muted-foreground" />
      </div>
    </div>
  )
}

/**
 * Bot Table Header
 */
function BotTableHeader() {
  return (
    <div className="grid grid-cols-[2fr_1fr_1fr_1fr_1fr_1fr_auto] gap-4 p-4 border-b bg-muted/30 text-sm text-muted-foreground font-medium">
      <div>Strategy</div>
      <div>Current Value</div>
      <div>Total PnL</div>
      <div>Bot Profit</div>
      <div>Avg Daily %</div>
      <div>Status</div>
      <div className="w-16"></div>
    </div>
  )
}

/**
 * History Row
 */
function HistoryRow({
  entry,
  onDelete,
}: {
  entry: BotHistoryEntry
  onDelete: (id: string) => void
}) {
  const isProfit = entry.totalProfit >= 0

  return (
    <div className="grid grid-cols-[2fr_1fr_1fr_1fr_1fr_auto] gap-4 items-center p-4 border-b hover:bg-muted/50">
      <div>
        <div className="font-medium">{entry.name}</div>
        <div className="text-sm text-muted-foreground">
          {entry.symbol} • {entry.exchange}
        </div>
      </div>

      <div>
        <div className="font-medium">${entry.totalInvested.toFixed(2)}</div>
      </div>

      <div className={getPnLTextColor(entry.totalProfit)}>
        <span className="font-semibold">
          {isProfit ? '+' : ''}${entry.totalProfit.toFixed(2)}
        </span>
        <span className="text-xs ml-1">
          ({isProfit ? '+' : ''}{entry.totalProfitPercent.toFixed(2)}%)
        </span>
      </div>

      <div>
        {entry.winRate.toFixed(1)}%
        <span className="text-xs text-muted-foreground ml-1">
          ({entry.totalTrades} trades)
        </span>
      </div>

      <div className="text-sm text-muted-foreground">
        {formatTradingTime(entry.tradingDurationSeconds)}
      </div>

      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 text-muted-foreground hover:text-red-500"
        onClick={(e) => {
          e.stopPropagation()
          onDelete(entry.id)
        }}
      >
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  )
}

/**
 * Bot Detail Panel (shown when a bot is selected)
 */
function BotDetailPanel({
  bot,
  onClose,
  onAction,
  onViewOrders,
  onModify,
}: {
  bot: Bot
  onClose: () => void
  onAction: (action: string) => void
  onViewOrders: () => void
  onModify: () => void
}) {
  const config = bot.configuration
  const perf = bot.performance
  const isActive = isBotActive(bot.state)
  const isFutures = config.botType.includes('futures')
  const baseAsset = bot.symbol.split('/')[0] || bot.symbol

  return (
    <div className="h-full overflow-y-auto">
      {/* Header */}
      <div className="p-4 border-b sticky top-0 bg-card z-10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-muted-foreground">COMBO Bot details</span>
          </div>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Bot Info Table */}
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Exchange</span>
            <div className="flex items-center gap-2">
              <span className="text-sm">{bot.exchange}</span>
              {isFutures && (
                <Badge variant="outline" className="bg-purple-500/10 text-purple-500 border-purple-500/30 text-xs">
                  Futures
                </Badge>
              )}
            </div>
          </div>
          
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Pair</span>
            <span className="text-sm font-medium">{bot.symbol}</span>
          </div>
          
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Direction</span>
            <span className={`text-sm font-medium ${
              config.positionMode === 'long' ? 'text-emerald-500' : 'text-red-500'
            }`}>
              {config.positionMode === 'long' ? 'Long' : 'Short'}
            </span>
          </div>
          
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Initial margin</span>
            <span className="text-sm">{config.investmentAmount.toLocaleString()} USDC</span>
          </div>
          
          {isFutures && (
            <>
              <div className="flex justify-between items-center">
                <span className="text-sm text-muted-foreground">Margin type</span>
                <span className="text-sm capitalize">{config.marginMode}</span>
              </div>
              
              <div className="flex justify-between items-center">
                <span className="text-sm text-muted-foreground">Leverage</span>
                <span className="text-sm">{config.leverage}x</span>
              </div>
            </>
          )}
          
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Profit currency</span>
            <span className="text-sm">USDC</span>
          </div>
        </div>

        <Separator />

        {/* DCA and Grid Orders */}
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">DCA orders</span>
            <span className="text-sm text-primary">+ {(perf.totalInvested * 0.8).toFixed(2)} {baseAsset}</span>
          </div>
          
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Grid orders</span>
            <span className="text-sm text-primary">+ {(perf.totalInvested * 0.65).toFixed(2)} {baseAsset}</span>
          </div>
        </div>

        <Separator />

        {/* Price Range */}
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">High price</span>
            <span className="text-sm">{((perf.currentPrice ?? 0) * 1.25).toFixed(4)}</span>
          </div>
          
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Low price</span>
            <span className="text-sm">{((perf.currentPrice ?? 0) * 0.75).toFixed(4)}</span>
          </div>
          
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">DCA & Grid levels</span>
            <span className="text-sm">{config.dcaConfig.averagingOrders?.ordersCount || 0}</span>
          </div>
          
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">DCA & Grid step</span>
            <span className="text-sm">{config.dcaConfig.averagingOrders?.stepPercent || 0}%</span>
          </div>
        </div>

        <Separator />

        {/* Risk Settings */}
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Stop Loss</span>
            <span className="text-sm">
              {config.dcaConfig.stopLoss?.enabled 
                ? `${config.dcaConfig.stopLoss.percent}%` 
                : '—'}
            </span>
          </div>
          
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Take Profit</span>
            <span className="text-sm">
              {config.dcaConfig.takeProfit?.enabled 
                ? `${config.dcaConfig.takeProfit.priceChangePercent}%` 
                : '—'}
            </span>
          </div>
        </div>

        <Separator />

        {/* Performance Stats */}
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Total PNL</span>
            <span className={`text-sm font-medium ${getPnLTextColor(perf.totalPnL)}`}>
              {perf.totalPnL >= 0 ? '+' : ''}{perf.totalPnL.toFixed(2)} ({perf.totalPnLPercent.toFixed(2)}%)
            </span>
          </div>
          
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Trading time</span>
            <span className="text-sm">{bot.tradingTimeDisplay || formatTradingTime(perf.tradingTimeSeconds)}</span>
          </div>
          
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Transactions</span>
            <span className="text-sm">{perf.totalTrades}</span>
          </div>
          
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Bot ID</span>
            <div className="flex items-center gap-1">
              <span className="text-xs font-mono text-muted-foreground truncate max-w-[120px]">
                {bot.id.slice(0, 20)}...
              </span>
              <Button variant="ghost" size="icon" className="h-6 w-6">
                <Eye className="h-3 w-3" />
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="sticky bottom-0 p-4 bg-card border-t space-y-2">
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
            onClick={() => onViewOrders()}
          >
            <Download className="h-4 w-4 mr-1" />
            Download logs (csv)
          </Button>
        </div>
        
        <Button 
          className="w-full bg-blue-600 hover:bg-blue-700"
          onClick={onViewOrders}
        >
          Bot orders
        </Button>
        
        <div className="grid grid-cols-3 gap-2">
          {isActive ? (
            <>
              <Button variant="outline" size="sm" onClick={() => onAction('pause')}>
                <Pause className="h-4 w-4" />
              </Button>
              <Button variant="destructive" size="sm" onClick={() => onAction('stop')}>
                <Square className="h-4 w-4" />
              </Button>
            </>
          ) : (
            <Button variant="default" size="sm" onClick={() => onAction('start')}>
              <Play className="h-4 w-4" />
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={onModify}>
            <Settings className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Main Page Component
// ============================================================================

export default function BotsPage() {
  const [activeTab, setActiveTab] = useState<'active' | 'history'>('active')
  const [stateFilter, setStateFilter] = useState<string>('')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedBot, setSelectedBot] = useState<Bot | null>(null)
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [isOrdersDialogOpen, setIsOrdersDialogOpen] = useState(false)
  const [isModifyDialogOpen, setIsModifyDialogOpen] = useState(false)
  const [isActionLoading, setIsActionLoading] = useState(false)
  const { toast } = useToast()

  // Hooks
  const { data: botsData, isLoading: botsLoading, refetch: refetchBots, createBot } = useBots({
    state: stateFilter || undefined,
    symbol: searchQuery || undefined,
  }, 30000) // Refresh every 30s

  const { data: historyData, isLoading: historyLoading, deleteEntry } = useBotHistory()
  const { data: historyStats } = useBotHistoryStats()

  // Handler for creating a new bot
  const handleCreateBot = useCallback(async (request: CreateBotRequest) => {
    await createBot(request)
    // Refetch will happen automatically in the hook
  }, [createBot])

  // Handler for modifying a bot
  const handleModifyBot = useCallback(async (botId: string, updates: UpdateBotRequest) => {
    try {
      await updateBotApi(botId, updates as unknown as Record<string, unknown>)
      toast({
        title: 'Bot Updated',
        description: `Bot configuration has been updated successfully.`,
      })
      refetchBots()
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to update bot'
      toast({
        title: 'Update Failed',
        description: message,
        variant: 'destructive',
      })
    }
  }, [refetchBots, toast])

  // Filter bots by search query (client-side for instant feedback)
  const filteredBots = useMemo((): Bot[] => {
    if (!botsData?.bots) return []
    if (!searchQuery) return botsData.bots as Bot[]

    const query = searchQuery.toLowerCase()
    return (botsData.bots as Bot[]).filter(
      (bot: Bot) =>
        bot.name.toLowerCase().includes(query) ||
        bot.symbol.toLowerCase().includes(query)
    )
  }, [botsData?.bots, searchQuery])

  // Calculate summary stats
  const summaryStats = useMemo(() => {
    if (!botsData?.bots) {
      return {
        totalBots: 0,
        activeBots: 0,
        totalPnL: 0,
        avgDaily: 0,
      }
    }

    const bots = botsData.bots as Bot[]
    const activeBots = bots.filter((b: Bot) => isBotActive(b.state)).length
    const totalPnL = bots.reduce((sum: number, b: Bot) => sum + b.performance.totalPnL, 0)
    const avgDaily =
      bots.length > 0
        ? bots.reduce((sum: number, b: Bot) => sum + b.performance.avgDailyProfit, 0) / bots.length
        : 0

    return {
      totalBots: bots.length,
      activeBots,
      totalPnL,
      avgDaily,
    }
  }, [botsData?.bots])

  const handleBotAction = useCallback(async (action: string) => {
    if (!selectedBot) return
    
    setIsActionLoading(true)
    try {
      // Map UI action string to API action format
      const actionMap: Record<string, BotActionRequest['action']> = {
        'start': 'start',
        'stop': 'stop',
        'pause': 'pause',
        'resume': 'resume',
        'close': 'close_position',
        'average': 'manual_average',
      }
      
      const apiAction = actionMap[action]
      if (!apiAction) {
        throw new Error(`Unknown action: ${action}`)
      }
      
      const result = await performBotAction(selectedBot.id, { action: apiAction })
      
      toast({
        title: 'Action Successful',
        description: result.message || `${action} completed for ${selectedBot.name}`,
      })
      
      refetchBots()
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Action failed'
      toast({
        title: 'Action Failed',
        description: message,
        variant: 'destructive',
      })
    } finally {
      setIsActionLoading(false)
    }
  }, [selectedBot, toast, refetchBots])

  const handleDeleteHistory = async (historyId: string) => {
    if (window.confirm('Are you sure you want to delete this history entry?')) {
      await deleteEntry(historyId)
    }
  }

  return (
    <ProtectedRoute>
      <AppShell>
        <div className="flex h-[calc(100vh-4rem)]">
          {/* Main Content */}
          <div className={`flex-1 overflow-y-auto ${selectedBot ? 'mr-[400px]' : ''}`}>
            <div className="p-6 space-y-6">
              {/* Page Header */}
              <div className="flex items-center justify-between">
                <div>
                  <h1 className="text-3xl font-bold tracking-tight">Bots</h1>
                  <p className="text-muted-foreground">
                    Manage your trading bots and view performance
                  </p>
                </div>
                <Button onClick={() => setIsCreateDialogOpen(true)}>
                  <Plus className="h-4 w-4 mr-2" />
                  Create Bot
                </Button>
              </div>

              {/* Summary Stats */}
              <div className="grid gap-4 md:grid-cols-4">
                <StatsCard
                  title="Active Bots"
                  value={summaryStats.activeBots.toString()}
                  subValue={`${summaryStats.totalBots} total`}
                  icon={Activity}
                />
                <StatsCard
                  title="Total PnL"
                  value={`$${summaryStats.totalPnL.toFixed(2)}`}
                  icon={TrendingUp}
                  trend={summaryStats.totalPnL >= 0 ? 'up' : 'down'}
                />
                <StatsCard
                  title="Avg Daily %"
                  value={`${summaryStats.avgDaily >= 0 ? '+' : ''}${summaryStats.avgDaily.toFixed(2)}%`}
                  icon={BarChart3}
                  trend={summaryStats.avgDaily >= 0 ? 'up' : 'down'}
                />
                <StatsCard
                  title="Historical Profit"
                  value={historyStats ? `$${historyStats.totalProfit}` : '$0'}
                  subValue={historyStats ? `${historyStats.totalBots} bots completed` : ''}
                  icon={History}
                />
              </div>

              {/* Tabs */}
              <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'active' | 'history')}>
                <div className="flex items-center justify-between">
                  <TabsList>
                    <TabsTrigger value="active" className="gap-2">
                      <BotIcon className="h-4 w-4" />
                      Active Bots
                      {botsData?.count !== undefined && (
                        <Badge variant="secondary" className="ml-1">
                          {botsData.count}
                        </Badge>
                      )}
                    </TabsTrigger>
                    <TabsTrigger value="history" className="gap-2">
                      <History className="h-4 w-4" />
                      History
                    </TabsTrigger>
                  </TabsList>

                  {/* Filters (only for active tab) */}
                  {activeTab === 'active' && (
                    <div className="flex items-center gap-2">
                      <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input
                          placeholder="Search bots..."
                          value={searchQuery}
                          onChange={(e) => setSearchQuery(e.target.value)}
                          className="pl-9 w-64"
                        />
                      </div>
                      <Select value={stateFilter} onValueChange={setStateFilter}>
                        <SelectTrigger className="w-36">
                          <SelectValue placeholder="All States" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="">All States</SelectItem>
                          <SelectItem value="running">Running</SelectItem>
                          <SelectItem value="paused">Paused</SelectItem>
                          <SelectItem value="stopped">Stopped</SelectItem>
                        </SelectContent>
                      </Select>
                      <Button variant="outline" size="icon" onClick={() => refetchBots()}>
                        <RefreshCw className="h-4 w-4" />
                      </Button>
                    </div>
                  )}
                </div>

                {/* Active Bots Tab */}
                <TabsContent value="active" className="mt-4">
                  <Card>
                    {botsLoading ? (
                      <div className="flex items-center justify-center py-12">
                        <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
                      </div>
                    ) : filteredBots.length === 0 ? (
                      <EmptyState
                        icon={BotIcon}
                        title="No bots found"
                        description={
                          searchQuery
                            ? 'Try adjusting your search or filters'
                            : 'Create your first trading bot to get started'
                        }
                        action={
                          !searchQuery && (
                            <Button onClick={() => setIsCreateDialogOpen(true)}>
                              <Plus className="h-4 w-4 mr-2" />
                              Create Bot
                            </Button>
                          )
                        }
                      />
                    ) : (
                      <>
                        <BotTableHeader />
                        {filteredBots.map((bot) => (
                          <BotRow
                            key={bot.id}
                            bot={bot}
                            onSelect={setSelectedBot}
                            isSelected={selectedBot?.id === bot.id}
                          />
                        ))}
                      </>
                    )}
                  </Card>
                </TabsContent>

                {/* History Tab */}
                <TabsContent value="history" className="mt-4">
                  <Card>
                    {historyLoading ? (
                      <div className="flex items-center justify-center py-12">
                        <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
                      </div>
                    ) : !historyData?.history || historyData.history.length === 0 ? (
                      <EmptyState
                        icon={History}
                        title="No history yet"
                        description="Completed bot runs will appear here"
                      />
                    ) : (
                      <>
                        <div className="grid grid-cols-[2fr_1fr_1fr_1fr_1fr_auto] gap-4 p-4 border-b bg-muted/30 text-sm text-muted-foreground font-medium">
                          <div>Bot</div>
                          <div>Invested</div>
                          <div>Profit</div>
                          <div>Win Rate</div>
                          <div>Duration</div>
                          <div className="w-8"></div>
                        </div>
                        {(historyData.history as BotHistoryEntry[]).map((entry: BotHistoryEntry) => (
                          <HistoryRow
                            key={entry.id}
                            entry={entry}
                            onDelete={handleDeleteHistory}
                          />
                        ))}
                      </>
                    )}
                  </Card>
                </TabsContent>
              </Tabs>
            </div>
          </div>

          {/* Detail Panel */}
          {selectedBot && (
            <div className="fixed right-0 top-16 bottom-0 w-[400px] border-l bg-card shadow-lg">
              <BotDetailPanel
                bot={selectedBot}
                onClose={() => setSelectedBot(null)}
                onAction={handleBotAction}
                onViewOrders={() => setIsOrdersDialogOpen(true)}
                onModify={() => setIsModifyDialogOpen(true)}
              />
            </div>
          )}

          {/* Create Bot Dialog */}
          <BotConfigDialog
            open={isCreateDialogOpen}
            onOpenChange={setIsCreateDialogOpen}
            onSubmit={handleCreateBot}
          />

          {/* Bot Orders Dialog */}
          <BotOrdersDialog
            open={isOrdersDialogOpen}
            onOpenChange={setIsOrdersDialogOpen}
            bot={selectedBot}
          />

          {/* Bot Modify Dialog */}
          <BotModifyDialog
            open={isModifyDialogOpen}
            onOpenChange={setIsModifyDialogOpen}
            bot={selectedBot}
            onSave={handleModifyBot}
          />
        </div>
      </AppShell>
    </ProtectedRoute>
  )
}
