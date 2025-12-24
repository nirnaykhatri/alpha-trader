/**
 * Order Entry Form Component
 * 
 * Professional order entry interface with symbol search, order type selection,
 * quantity/price inputs, and real-time validation.
 * 
 * @module components/trading/order-form
 */

'use client'

import React, { useState, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { AlertTriangle, TrendingUp, TrendingDown, DollarSign, Info } from 'lucide-react'

type OrderSide = 'buy' | 'sell'
type OrderType = 'market' | 'limit' | 'stop' | 'stop_limit'
type TimeInForce = 'day' | 'gtc' | 'ioc' | 'fok'

interface OrderFormData {
  symbol: string
  side: OrderSide
  type: OrderType
  quantity: string
  limitPrice: string
  stopPrice: string
  timeInForce: TimeInForce
  extendedHours: boolean
}

interface OrderFormProps {
  onSubmit: (order: OrderFormData) => Promise<void>
  initialSymbol?: string
  initialSide?: OrderSide
  isLoading?: boolean
  currentPrice?: number
  symbolInfo?: {
    name: string
    lastPrice: number
    change: number
    changePercent: number
    bidPrice: number
    askPrice: number
    volume: number
  }
}

const initialFormData: OrderFormData = {
  symbol: '',
  side: 'buy',
  type: 'market',
  quantity: '',
  limitPrice: '',
  stopPrice: '',
  timeInForce: 'day',
  extendedHours: false,
}

/**
 * Order Preview Component
 * 
 * Shows estimated order details before submission
 */
function OrderPreview({
  formData,
  currentPrice,
}: {
  formData: OrderFormData
  currentPrice?: number
}) {
  const quantity = parseFloat(formData.quantity) || 0
  const price = formData.type === 'market' 
    ? (currentPrice || 0) 
    : parseFloat(formData.limitPrice) || currentPrice || 0
  const estimatedTotal = quantity * price

  return (
    <div className="rounded-lg bg-muted/50 p-4 space-y-3">
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">Order Type</span>
        <span className="font-medium capitalize">{formData.type.replace('_', ' ')}</span>
      </div>
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">Quantity</span>
        <span className="font-medium">{quantity || '—'} shares</span>
      </div>
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">Est. Price</span>
        <span className="font-medium">${price.toFixed(2)}</span>
      </div>
      <Separator />
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground font-medium">Est. Total</span>
        <span className="text-lg font-bold">
          ${estimatedTotal.toLocaleString(undefined, { minimumFractionDigits: 2 })}
        </span>
      </div>
    </div>
  )
}

/**
 * Symbol Info Header Component
 */
function SymbolHeader({ info }: { info: NonNullable<OrderFormProps['symbolInfo']> }) {
  const isPositive = info.change >= 0

  return (
    <div className="flex items-center justify-between p-4 rounded-lg bg-muted/30">
      <div>
        <h3 className="text-2xl font-bold">{info.name}</h3>
        <p className="text-3xl font-bold">${info.lastPrice.toFixed(2)}</p>
      </div>
      <div className="text-right">
        <div
          className={cn(
            'flex items-center gap-1 text-lg font-semibold',
            isPositive ? 'text-profit' : 'text-loss'
          )}
        >
          {isPositive ? <TrendingUp className="h-5 w-5" /> : <TrendingDown className="h-5 w-5" />}
          <span>
            {isPositive ? '+' : ''}
            {info.change.toFixed(2)} ({info.changePercent.toFixed(2)}%)
          </span>
        </div>
        <div className="text-sm text-muted-foreground mt-1">
          Bid: ${info.bidPrice.toFixed(2)} • Ask: ${info.askPrice.toFixed(2)}
        </div>
        <div className="text-sm text-muted-foreground">
          Vol: {(info.volume / 1000000).toFixed(2)}M
        </div>
      </div>
    </div>
  )
}

/**
 * Order Form Component
 * 
 * Comprehensive order entry interface with validation and preview.
 * 
 * @param {OrderFormProps} props - Component props
 * @returns {JSX.Element} Order form
 */
export function OrderForm({
  onSubmit,
  initialSymbol = '',
  initialSide = 'buy',
  isLoading = false,
  currentPrice,
  symbolInfo,
}: OrderFormProps): JSX.Element {
  const [formData, setFormData] = useState<OrderFormData>({
    ...initialFormData,
    symbol: initialSymbol,
    side: initialSide,
  })
  const [errors, setErrors] = useState<Partial<Record<keyof OrderFormData, string>>>({})

  const updateField = useCallback(
    <K extends keyof OrderFormData>(field: K, value: OrderFormData[K]) => {
      setFormData((prev) => ({ ...prev, [field]: value }))
      setErrors((prev) => ({ ...prev, [field]: undefined }))
    },
    []
  )

  const validate = useCallback((): boolean => {
    const newErrors: typeof errors = {}

    if (!formData.symbol.trim()) {
      newErrors.symbol = 'Symbol is required'
    }

    const quantity = parseFloat(formData.quantity)
    if (!formData.quantity || isNaN(quantity) || quantity <= 0) {
      newErrors.quantity = 'Valid quantity is required'
    }

    if (formData.type === 'limit' || formData.type === 'stop_limit') {
      const limitPrice = parseFloat(formData.limitPrice)
      if (!formData.limitPrice || isNaN(limitPrice) || limitPrice <= 0) {
        newErrors.limitPrice = 'Valid limit price is required'
      }
    }

    if (formData.type === 'stop' || formData.type === 'stop_limit') {
      const stopPrice = parseFloat(formData.stopPrice)
      if (!formData.stopPrice || isNaN(stopPrice) || stopPrice <= 0) {
        newErrors.stopPrice = 'Valid stop price is required'
      }
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }, [formData])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validate()) return
    await onSubmit(formData)
  }

  const needsLimitPrice = formData.type === 'limit' || formData.type === 'stop_limit'
  const needsStopPrice = formData.type === 'stop' || formData.type === 'stop_limit'

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {symbolInfo && <SymbolHeader info={symbolInfo} />}

      {/* Side Selection */}
      <div className="grid grid-cols-2 gap-2">
        <Button
          type="button"
          variant={formData.side === 'buy' ? 'success' : 'outline'}
          className={cn('h-14 text-lg font-semibold', formData.side === 'buy' && 'shadow-lg')}
          onClick={() => updateField('side', 'buy')}
        >
          <TrendingUp className="mr-2 h-5 w-5" />
          Buy
        </Button>
        <Button
          type="button"
          variant={formData.side === 'sell' ? 'danger' : 'outline'}
          className={cn('h-14 text-lg font-semibold', formData.side === 'sell' && 'shadow-lg')}
          onClick={() => updateField('side', 'sell')}
        >
          <TrendingDown className="mr-2 h-5 w-5" />
          Sell
        </Button>
      </div>

      {/* Symbol Input */}
      <div className="space-y-2">
        <Label htmlFor="symbol">Symbol</Label>
        <Input
          id="symbol"
          placeholder="e.g., AAPL, MSFT, GOOGL"
          value={formData.symbol}
          onChange={(e) => updateField('symbol', e.target.value.toUpperCase())}
          error={!!errors.symbol}
          errorMessage={errors.symbol}
          className="text-lg font-medium uppercase"
        />
      </div>

      {/* Order Type */}
      <div className="space-y-2">
        <Label>Order Type</Label>
        <Select value={formData.type} onValueChange={(v) => updateField('type', v as OrderType)}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="market">Market Order</SelectItem>
            <SelectItem value="limit">Limit Order</SelectItem>
            <SelectItem value="stop">Stop Order</SelectItem>
            <SelectItem value="stop_limit">Stop Limit Order</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Quantity */}
      <div className="space-y-2">
        <Label htmlFor="quantity">Quantity (Shares)</Label>
        <Input
          id="quantity"
          type="number"
          min="1"
          step="1"
          placeholder="Number of shares"
          value={formData.quantity}
          onChange={(e) => updateField('quantity', e.target.value)}
          error={!!errors.quantity}
          errorMessage={errors.quantity}
          icon={<DollarSign className="h-4 w-4" />}
        />
      </div>

      {/* Limit Price */}
      {needsLimitPrice && (
        <div className="space-y-2">
          <Label htmlFor="limitPrice">Limit Price</Label>
          <Input
            id="limitPrice"
            type="number"
            min="0.01"
            step="0.01"
            placeholder="0.00"
            value={formData.limitPrice}
            onChange={(e) => updateField('limitPrice', e.target.value)}
            error={!!errors.limitPrice}
            errorMessage={errors.limitPrice}
            icon={<DollarSign className="h-4 w-4" />}
          />
        </div>
      )}

      {/* Stop Price */}
      {needsStopPrice && (
        <div className="space-y-2">
          <Label htmlFor="stopPrice">Stop Price</Label>
          <Input
            id="stopPrice"
            type="number"
            min="0.01"
            step="0.01"
            placeholder="0.00"
            value={formData.stopPrice}
            onChange={(e) => updateField('stopPrice', e.target.value)}
            error={!!errors.stopPrice}
            errorMessage={errors.stopPrice}
            icon={<DollarSign className="h-4 w-4" />}
          />
        </div>
      )}

      {/* Time in Force */}
      <div className="space-y-2">
        <Label>Time in Force</Label>
        <Select
          value={formData.timeInForce}
          onValueChange={(v) => updateField('timeInForce', v as TimeInForce)}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="day">Day</SelectItem>
            <SelectItem value="gtc">Good Till Canceled (GTC)</SelectItem>
            <SelectItem value="ioc">Immediate or Cancel (IOC)</SelectItem>
            <SelectItem value="fok">Fill or Kill (FOK)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Extended Hours */}
      <div className="flex items-center justify-between rounded-lg border border-border/50 p-4">
        <div className="space-y-0.5">
          <Label htmlFor="extendedHours" className="text-base">
            Extended Hours
          </Label>
          <p className="text-sm text-muted-foreground">Allow trading outside market hours</p>
        </div>
        <Switch
          id="extendedHours"
          checked={formData.extendedHours}
          onCheckedChange={(v) => updateField('extendedHours', v)}
        />
      </div>

      <Separator />

      {/* Order Preview */}
      <OrderPreview formData={formData} currentPrice={currentPrice} />

      {/* Warning for Market Orders */}
      {formData.type === 'market' && (
        <div className="flex items-start gap-3 rounded-lg bg-warning/10 p-4 text-warning">
          <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium">Market Order Warning</p>
            <p className="text-warning/80">
              Market orders execute immediately at the best available price, which may differ from
              the displayed price.
            </p>
          </div>
        </div>
      )}

      {/* Submit Button */}
      <Button
        type="submit"
        variant={formData.side === 'buy' ? 'success' : 'danger'}
        className="w-full h-14 text-lg font-semibold"
        loading={isLoading}
        disabled={isLoading}
      >
        {formData.side === 'buy' ? 'Place Buy Order' : 'Place Sell Order'}
      </Button>
    </form>
  )
}

export default OrderForm
