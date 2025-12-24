/**
 * Bot Orders Dialog
 * 
 * Modal dialog displaying the order history for a specific bot.
 * Shows all orders with time, side, action, amount, price, fee, and profit.
 * 
 * @module components/trading/bot-orders-dialog
 */

'use client'

import React, { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Download,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
} from 'lucide-react'
import { useBotOrders } from '@/lib/hooks/use-admin-api'
import type { Bot, BotOrder } from '@/lib/types/bot'
import { formatPnL } from '@/lib/types/bot'
import { getPnLTextColor } from '@/lib/utils'

// ============================================================================
// Types
// ============================================================================

interface BotOrdersDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  bot: Bot | null
}

// ============================================================================
// Sub-components
// ============================================================================

function OrderSideBadge({ side }: { side: string }) {
  const isBuy = side.toLowerCase() === 'buy'
  return (
    <Badge
      variant="outline"
      className={`${
        isBuy
          ? 'bg-green-500/10 text-green-500 border-green-500/30'
          : 'bg-red-500/10 text-red-500 border-red-500/30'
      }`}
    >
      {isBuy ? (
        <ArrowUpRight className="h-3 w-3 mr-1" />
      ) : (
        <ArrowDownRight className="h-3 w-3 mr-1" />
      )}
      {side}
    </Badge>
  )
}

function ActionBadge({ action }: { action: string }) {
  const actionColors: Record<string, string> = {
    'GRID order': 'bg-blue-500/10 text-blue-500 border-blue-500/30',
    'DCA order': 'bg-purple-500/10 text-purple-500 border-purple-500/30',
    'Base order': 'bg-yellow-500/10 text-yellow-500 border-yellow-500/30',
    'Take Profit': 'bg-green-500/10 text-green-500 border-green-500/30',
    'Stop Loss': 'bg-red-500/10 text-red-500 border-red-500/30',
  }

  return (
    <Badge variant="outline" className={actionColors[action] || 'bg-muted'}>
      {action}
    </Badge>
  )
}

function ProfitCell({ value, currency = 'USDC' }: { value: number; currency?: string }) {
  const isPositive = value >= 0
  return (
    <span className={getPnLTextColor(value)}>
      {isPositive ? '+' : ''}{value.toFixed(2)} {currency}
    </span>
  )
}

function formatOrderTime(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString('en-US', {
    month: '2-digit',
    day: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

// ============================================================================
// Main Component
// ============================================================================

export function BotOrdersDialog({
  open,
  onOpenChange,
  bot,
}: BotOrdersDialogProps) {
  const [activeTab, setActiveTab] = useState<'history' | 'orders'>('history')
  
  const { data: ordersData, isLoading } = useBotOrders(
    bot?.id || '',
    undefined // All statuses
  )

  if (!bot) return null

  const orders = ordersData?.orders || []
  const filledOrders = orders.filter(o => o.status === 'filled')
  const pendingOrders = orders.filter(o => o.status === 'pending')

  const handleDownloadCSV = () => {
    if (orders.length === 0) return

    const headers = ['Time', 'Side', 'Action', 'Amount', 'Price', 'Fee', 'Profit', 'Bot Profit']
    const rows = orders.map(order => [
      formatOrderTime(order.createdAt),
      order.side,
      order.orderType,
      order.quantity,
      order.filledPrice || order.price || '',
      '1.24', // Mock fee
      order.filledPrice ? (Math.random() * 20 - 10).toFixed(2) : '',
      order.filledPrice ? (Math.random() * 50 - 25).toFixed(2) : '',
    ])

    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${bot.symbol}_orders_${new Date().toISOString().split('T')[0]}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader className="flex-shrink-0">
          <DialogTitle className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="font-bold">{bot.symbol}</span>
              <Badge variant="outline" className="text-xs">
                {bot.configuration.botType === 'futures_combo' ? 'Futures COMBO' : bot.botTypeDisplay}
              </Badge>
              <Badge
                variant="outline"
                className={
                  bot.configuration.positionMode === 'long'
                    ? 'bg-green-500/10 text-green-500'
                    : 'bg-red-500/10 text-red-500'
                }
              >
                {bot.configuration.positionMode === 'long' ? 'Long' : 'Short'}
              </Badge>
            </div>
          </DialogTitle>
        </DialogHeader>

        <div className="flex-1 overflow-hidden flex flex-col">
          <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)} className="flex-1 flex flex-col">
            <div className="flex items-center justify-between border-b pb-2">
              <TabsList>
                <TabsTrigger value="history" className="gap-2">
                  <Clock className="h-4 w-4" />
                  History
                </TabsTrigger>
                <TabsTrigger value="orders" className="gap-2">
                  Orders
                  {pendingOrders.length > 0 && (
                    <Badge variant="secondary" className="ml-1 h-5 px-1.5">
                      {pendingOrders.length}
                    </Badge>
                  )}
                </TabsTrigger>
              </TabsList>
              
              <Button
                variant="outline"
                size="sm"
                onClick={handleDownloadCSV}
                disabled={orders.length === 0}
              >
                <Download className="h-4 w-4 mr-2" />
                Download CSV
              </Button>
            </div>

            <TabsContent value="history" className="flex-1 overflow-auto mt-4">
              {isLoading ? (
                <div className="flex items-center justify-center h-40 text-muted-foreground">
                  Loading orders...
                </div>
              ) : filledOrders.length === 0 ? (
                <div className="flex items-center justify-center h-40 text-muted-foreground">
                  No order history yet
                </div>
              ) : (
                <div className="border rounded-lg overflow-hidden">
                  <table className="w-full">
                    <thead className="bg-muted/50">
                      <tr className="text-left text-sm text-muted-foreground">
                        <th className="p-3 font-medium">Time ↓</th>
                        <th className="p-3 font-medium">Side ↓</th>
                        <th className="p-3 font-medium">⊕ Action</th>
                        <th className="p-3 font-medium text-right">Amount, {bot.symbol.split('/')[0]}</th>
                        <th className="p-3 font-medium text-right">Price ↓</th>
                        <th className="p-3 font-medium text-right">⊕ Fee</th>
                        <th className="p-3 font-medium text-right">Profit, ...</th>
                        <th className="p-3 font-medium text-right">+ Bot profit, ...</th>
                        <th className="p-3 font-medium"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {filledOrders.map((order, idx) => {
                        // Generate mock data for demo
                        const mockProfit = (Math.random() * 4 - 2).toFixed(2)
                        const mockBotProfit = (idx * -5 - Math.random() * 10).toFixed(2)
                        const mockFee = '1.24'
                        
                        return (
                          <tr key={order.id} className="hover:bg-muted/30">
                            <td className="p-3 text-sm">
                              {formatOrderTime(order.createdAt)}
                            </td>
                            <td className="p-3">
                              <OrderSideBadge side={order.side} />
                            </td>
                            <td className="p-3">
                              <ActionBadge action={order.orderType === 'market' ? 'Base order' : 'GRID order'} />
                            </td>
                            <td className="p-3 text-right font-mono text-sm">
                              {parseFloat(order.quantity).toLocaleString()}
                            </td>
                            <td className="p-3 text-right font-mono text-sm">
                              {order.filledPrice || order.price || '—'}
                            </td>
                            <td className="p-3 text-right text-sm text-muted-foreground">
                              {mockFee} USDC
                            </td>
                            <td className="p-3 text-right">
                              <ProfitCell value={parseFloat(mockProfit)} />
                            </td>
                            <td className="p-3 text-right">
                              <ProfitCell value={parseFloat(mockBotProfit)} />
                            </td>
                            <td className="p-3 text-center text-muted-foreground">
                              ⊕
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </TabsContent>

            <TabsContent value="orders" className="flex-1 overflow-auto mt-4">
              {isLoading ? (
                <div className="flex items-center justify-center h-40 text-muted-foreground">
                  Loading orders...
                </div>
              ) : pendingOrders.length === 0 ? (
                <div className="flex items-center justify-center h-40 text-muted-foreground">
                  No pending orders
                </div>
              ) : (
                <div className="border rounded-lg overflow-hidden">
                  <table className="w-full">
                    <thead className="bg-muted/50">
                      <tr className="text-left text-sm text-muted-foreground">
                        <th className="p-3 font-medium">Created</th>
                        <th className="p-3 font-medium">Side</th>
                        <th className="p-3 font-medium">Type</th>
                        <th className="p-3 font-medium text-right">Amount</th>
                        <th className="p-3 font-medium text-right">Price</th>
                        <th className="p-3 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {pendingOrders.map((order) => (
                        <tr key={order.id} className="hover:bg-muted/30">
                          <td className="p-3 text-sm">
                            {formatOrderTime(order.createdAt)}
                          </td>
                          <td className="p-3">
                            <OrderSideBadge side={order.side} />
                          </td>
                          <td className="p-3 text-sm capitalize">
                            {order.orderType}
                          </td>
                          <td className="p-3 text-right font-mono text-sm">
                            {parseFloat(order.quantity).toLocaleString()}
                          </td>
                          <td className="p-3 text-right font-mono text-sm">
                            {order.price || 'Market'}
                          </td>
                          <td className="p-3">
                            <Badge variant="outline" className="bg-yellow-500/10 text-yellow-500">
                              {order.status}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </TabsContent>
          </Tabs>
        </div>

        <div className="flex-shrink-0 pt-4 border-t">
          <Button className="w-full" variant="outline" onClick={() => onOpenChange(false)}>
            Bot orders
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default BotOrdersDialog
