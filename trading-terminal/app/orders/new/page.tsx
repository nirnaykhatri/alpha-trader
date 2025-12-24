/**
 * New Order Page
 * 
 * Manual order entry interface for placing buy/sell orders.
 * 
 * @module app/orders/new/page
 */

'use client'

import React from 'react'
import { AppShell } from '@/components/layout'
import { ProtectedRoute } from '@/components/auth'
import { OrderForm } from '@/components/trading'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui'
import { TrendingUp, Clock, Wallet, Target } from 'lucide-react'
import { placeOrder, type OrderRequest } from '@/lib/admin-api'
import { useToast } from '@/components/ui'
import { formatCurrency } from '@/lib/utils'

/** Quote data for a symbol */
interface Quote {
  symbol: string
  bid: number
  ask: number
  last: number
  change: number
  changePercent: number
  volume: number
  high: number
  low: number
  open: number
  prevClose: number
}

/** Mock quote for demonstration */
const mockQuote: Quote = {
  symbol: 'AAPL',
  bid: 182.43,
  ask: 182.47,
  last: 182.45,
  change: 2.15,
  changePercent: 1.19,
  volume: 45678900,
  high: 183.50,
  low: 180.25,
  open: 180.50,
  prevClose: 180.30,
}

/** Mock account info */
const mockAccount = {
  buyingPower: 45000,
  cashAvailable: 32000,
  portfolioValue: 127543.82,
}

/**
 * Formats a large number with suffixes
 */
function formatVolume(value: number): string {
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(2)}M`
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(2)}K`
  }
  return value.toString()
}

/**
 * QuoteCard Component
 * 
 * Displays real-time quote data for a symbol.
 */
function QuoteCard({ quote }: { quote: Quote }) {
  const isPositive = quote.change >= 0

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">{quote.symbol}</CardTitle>
          <span className={`text-sm font-medium ${isPositive ? 'text-emerald-500' : 'text-red-500'}`}>
            {isPositive ? '+' : ''}{quote.change.toFixed(2)} ({isPositive ? '+' : ''}{quote.changePercent.toFixed(2)}%)
          </span>
        </div>
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-bold mb-4">
          {formatCurrency(quote.last)}
        </div>
        
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-muted-foreground">Bid</p>
            <p className="font-medium">{formatCurrency(quote.bid)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Ask</p>
            <p className="font-medium">{formatCurrency(quote.ask)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">High</p>
            <p className="font-medium">{formatCurrency(quote.high)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Low</p>
            <p className="font-medium">{formatCurrency(quote.low)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Open</p>
            <p className="font-medium">{formatCurrency(quote.open)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Prev Close</p>
            <p className="font-medium">{formatCurrency(quote.prevClose)}</p>
          </div>
        </div>

        <div className="mt-4 pt-4 border-t border-border">
          <p className="text-xs text-muted-foreground">Volume</p>
          <p className="font-medium">{formatVolume(quote.volume)}</p>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * AccountInfo Component
 * 
 * Displays account balance and buying power.
 */
function AccountInfo() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Wallet className="h-4 w-4" />
          Account Info
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex justify-between items-center">
          <span className="text-sm text-muted-foreground">Buying Power</span>
          <span className="font-medium">{formatCurrency(mockAccount.buyingPower)}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-sm text-muted-foreground">Cash Available</span>
          <span className="font-medium">{formatCurrency(mockAccount.cashAvailable)}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-sm text-muted-foreground">Portfolio Value</span>
          <span className="font-medium">{formatCurrency(mockAccount.portfolioValue)}</span>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * RecentOrders Component
 * 
 * Displays recent orders for quick reference.
 */
function RecentOrders() {
  const recentOrders = [
    { symbol: 'NVDA', side: 'buy', qty: 10, price: 725.00, status: 'filled' },
    { symbol: 'AAPL', side: 'sell', qty: 20, price: 182.50, status: 'filled' },
    { symbol: 'MSFT', side: 'buy', qty: 15, price: 415.00, status: 'pending' },
  ]

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Clock className="h-4 w-4" />
          Recent Orders
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {recentOrders.map((order, index) => (
            <div key={index} className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  order.side === 'buy' ? 'bg-emerald-500/20 text-emerald-500' : 'bg-red-500/20 text-red-500'
                }`}>
                  {order.side.toUpperCase()}
                </span>
                <span className="font-medium">{order.symbol}</span>
              </div>
              <div className="text-right">
                <div>{order.qty} @ {formatCurrency(order.price)}</div>
                <div className={`text-xs ${
                  order.status === 'filled' ? 'text-emerald-500' : 'text-yellow-500'
                }`}>
                  {order.status}
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * QuickSymbols Component
 * 
 * Quick access buttons for frequently traded symbols.
 */
function QuickSymbols({ onSelect }: { onSelect: (symbol: string) => void }) {
  const symbols = ['AAPL', 'NVDA', 'MSFT', 'TSLA', 'AMD', 'GOOGL', 'META', 'AMZN']

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Target className="h-4 w-4" />
          Quick Symbols
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-2">
          {symbols.map((symbol) => (
            <button
              key={symbol}
              onClick={() => onSelect(symbol)}
              className="px-3 py-1.5 text-sm font-medium bg-muted hover:bg-muted/80 rounded-md transition-colors"
            >
              {symbol}
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * New Order Page Component
 * 
 * Provides the interface for manual order entry.
 */
export default function NewOrderPage() {
  const [selectedSymbol, setSelectedSymbol] = React.useState('AAPL')
  const [isSubmitting, setIsSubmitting] = React.useState(false)
  const { toast } = useToast()

  const handleOrderSubmit = async (order: {
    symbol: string
    side: 'buy' | 'sell'
    type: string
    quantity: string
    limitPrice: string
    stopPrice: string
    timeInForce: 'day' | 'gtc' | 'ioc' | 'fok'
    extendedHours: boolean
  }) => {
    setIsSubmitting(true)
    
    try {
      // Map frontend order format to API request format
      const orderRequest: OrderRequest = {
        symbol: order.symbol,
        side: order.side,
        type: order.type,
        qty: order.quantity,
        time_in_force: order.timeInForce,
        extended_hours: order.extendedHours,
        ...(order.limitPrice && { limit_price: order.limitPrice }),
        ...(order.stopPrice && { stop_price: order.stopPrice }),
      }
      
      const result = await placeOrder(orderRequest)
      
      toast({
        title: 'Order Placed Successfully',
        description: `${order.side.toUpperCase()} ${order.quantity} ${order.symbol} - Order ID: ${result.order_id || 'pending'}`,
        variant: 'default',
      })
      
      console.log('Order placed:', result)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to place order'
      toast({
        title: 'Order Failed',
        description: message,
        variant: 'destructive',
      })
      console.error('Order submission error:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <ProtectedRoute>
      <AppShell>
        <div className="space-y-6">
          {/* Page Header */}
          <div>
            <h1 className="text-3xl font-bold tracking-tight">New Order</h1>
            <p className="text-muted-foreground">
              Place a new trade order manually
            </p>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            {/* Order Form - Takes up 2 columns */}
            <div className="lg:col-span-2">
              <OrderForm 
                initialSymbol={selectedSymbol}
                onSubmit={handleOrderSubmit}
                isLoading={isSubmitting}
              />
            </div>

            {/* Sidebar */}
            <div className="space-y-6">
              <QuoteCard quote={mockQuote} />
              <AccountInfo />
              <QuickSymbols onSelect={setSelectedSymbol} />
              <RecentOrders />
            </div>
          </div>
        </div>
      </AppShell>
    </ProtectedRoute>
  )
}
