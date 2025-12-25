/**
 * Bot Modify Dialog
 * 
 * Slide-out panel for modifying an existing bot's settings.
 * Allows editing strategy direction, investment, leverage, margin,
 * price range, DCA/Grid settings, stop loss, and take profit.
 * 
 * @module components/trading/bot-modify-dialog
 */

'use client'

import React, { useState, useCallback, useEffect } from 'react'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import {
  X,
  TrendingUp,
  TrendingDown,
  ChevronDown,
  AlertTriangle,
} from 'lucide-react'
import type { Bot, UpdateBotRequest } from '@/lib/types/bot'
import { BOT_TYPE_LABELS } from '@/lib/types/bot'

// ============================================================================
// Types
// ============================================================================

interface BotModifyDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  bot: Bot | null
  onSave: (botId: string, updates: UpdateBotRequest) => Promise<void>
}

interface ModifyFormState {
  // Strategy
  positionMode: 'long' | 'short'
  
  // Investment
  investmentAmount: string
  leverage: number
  marginMode: 'isolated' | 'cross'
  
  // Price Range
  lowPrice: string
  highPrice: string
  step: string
  gridLevels: number
  
  // Position Limits
  maxPosition: string
  maxMargin: string
  tpOrder: string
  dcaOrders: string
  gridOrders: string
  
  // Risk Management
  stopLossEnabled: boolean
  stopLossType: 'pnl' | 'price'
  stopLossValue: string
  
  takeProfitEnabled: boolean
  takeProfitType: 'pnl' | 'price'
  takeProfitValue: string
}

// ============================================================================
// Component
// ============================================================================

export function BotModifyDialog({
  open,
  onOpenChange,
  bot,
  onSave,
}: BotModifyDialogProps) {
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  const [form, setForm] = useState<ModifyFormState>({
    positionMode: 'long',
    investmentAmount: '2071',
    leverage: 3,
    marginMode: 'isolated',
    lowPrice: '0.1404',
    highPrice: '0.2381',
    step: '1.81',
    gridLevels: 30,
    maxPosition: '48773.29',
    maxMargin: '16257.76',
    tpOrder: '16267.76',
    dcaOrders: '19583.50',
    gridOrders: '16257.76',
    stopLossEnabled: true,
    stopLossType: 'price',
    stopLossValue: '0.0954',
    takeProfitEnabled: true,
    takeProfitType: 'pnl',
    takeProfitValue: '7',
  })

  // Initialize form from bot data
  useEffect(() => {
    if (bot) {
      setForm(prev => ({
        ...prev,
        positionMode: bot.configuration.positionMode === 'short' ? 'short' : 'long',
        investmentAmount: bot.configuration.investmentAmount.toString(),
        leverage: bot.configuration.leverage || 3,
        marginMode: bot.configuration.marginMode === 'cross' ? 'cross' : 'isolated',
        stopLossEnabled: bot.configuration.dcaConfig.stopLoss?.enabled ?? false,
        stopLossValue: bot.configuration.dcaConfig.stopLoss?.percent?.toString() || '5.0',
        takeProfitEnabled: bot.configuration.dcaConfig.takeProfit?.enabled ?? true,
        takeProfitValue: bot.configuration.dcaConfig.takeProfit?.priceChangePercent?.toString() || '1.0',
      }))
    }
  }, [bot])

  const updateForm = useCallback(<K extends keyof ModifyFormState>(
    key: K,
    value: ModifyFormState[K]
  ) => {
    setForm(prev => ({ ...prev, [key]: value }))
    setError(null)
  }, [])

  const handleSave = async () => {
    if (!bot) return

    setIsSubmitting(true)
    setError(null)

    try {
      await onSave(bot.id, {
        dcaConfig: {
          ...bot.configuration.dcaConfig,
          stopLoss: {
            ...bot.configuration.dcaConfig.stopLoss,
            enabled: form.stopLossEnabled,
            percent: parseFloat(form.stopLossValue),
          },
          takeProfit: {
            ...bot.configuration.dcaConfig.takeProfit,
            enabled: form.takeProfitEnabled,
            priceChangePercent: parseFloat(form.takeProfitValue),
          },
        },
      })
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update bot')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (!bot) return null

  const symbol = bot.symbol
  const baseAsset = symbol.split('/')[0] || symbol

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[400px] sm:w-[450px] overflow-y-auto">
        <SheetHeader className="space-y-3">
          <div className="flex items-center justify-between">
            <SheetTitle className="text-lg">Modify {BOT_TYPE_LABELS[bot.configuration.botType]}</SheetTitle>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => onOpenChange(false)}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
          
          {/* Exchange and Symbol Info */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded-full bg-blue-500/20 flex items-center justify-center">
                <span className="text-xs font-bold text-blue-500">CB</span>
              </div>
              <span className="text-sm text-muted-foreground">Coinbase</span>
              <Badge variant="outline" className="bg-purple-500/10 text-purple-500 border-purple-500/30">
                Futures
              </Badge>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded-full bg-gradient-to-r from-blue-500 to-purple-500" />
            <span className="font-medium">{symbol}</span>
          </div>
        </SheetHeader>

        <div className="space-y-6 py-6">
          {/* Strategy Direction */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">⊕</span>
              <Label className="text-sm">Strategy</Label>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant={form.positionMode === 'long' ? 'default' : 'outline'}
                onClick={() => updateForm('positionMode', 'long')}
                className={`${
                  form.positionMode === 'long'
                    ? 'bg-green-500 hover:bg-green-600 text-white'
                    : ''
                }`}
              >
                <TrendingUp className="h-4 w-4 mr-2" />
                Long
              </Button>
              <Button
                variant={form.positionMode === 'short' ? 'default' : 'outline'}
                onClick={() => updateForm('positionMode', 'short')}
                className={`${
                  form.positionMode === 'short'
                    ? 'bg-red-500 hover:bg-red-600 text-white'
                    : ''
                }`}
              >
                <TrendingDown className="h-4 w-4 mr-2" />
                Short
              </Button>
            </div>
          </div>

          {/* Investment Amount */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-sm">∟ Investment, USDT</Label>
              <span className="text-sm text-muted-foreground">2 101 USD</span>
            </div>
            <Input
              type="text"
              value={form.investmentAmount}
              onChange={(e) => updateForm('investmentAmount', e.target.value)}
              className="font-mono"
            />
            
            {/* Investment Slider */}
            <div className="pt-2">
              <Slider
                value={[parseFloat(form.investmentAmount) || 0]}
                onValueChange={([v]) => updateForm('investmentAmount', v.toFixed(0))}
                min={100}
                max={10000}
                step={100}
                className="w-full"
              />
              <div className="flex justify-between text-xs text-muted-foreground mt-1">
                <span>48.5%</span>
              </div>
            </div>
          </div>

          {/* Leverage and Margin Mode */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label className="text-sm">Leverage</Label>
              <Button variant="outline" className="w-full justify-between">
                {form.leverage}.00x
                <ChevronDown className="h-4 w-4 ml-2" />
              </Button>
            </div>
            <div className="space-y-2">
              <Label className="text-sm">Margin</Label>
              <div className="flex gap-1">
                <Button
                  variant={form.marginMode === 'isolated' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => updateForm('marginMode', 'isolated')}
                  className="flex-1"
                >
                  Isolated
                </Button>
                <Button
                  variant={form.marginMode === 'cross' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => updateForm('marginMode', 'cross')}
                  className="flex-1"
                >
                  Cross
                </Button>
              </div>
            </div>
          </div>

          {/* Manual Adjustment Link */}
          <div className="flex justify-end">
            <Button variant="link" className="text-primary text-sm p-0 h-auto">
              Manual adjustment →
            </Button>
          </div>

          <Separator />

          {/* Price Range */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="text-sm text-muted-foreground">Low price</Label>
              <Input
                value={form.lowPrice}
                onChange={(e) => updateForm('lowPrice', e.target.value)}
                className="font-mono"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm text-muted-foreground">⊕ High price</Label>
              <Input
                value={form.highPrice}
                onChange={(e) => updateForm('highPrice', e.target.value)}
                className="font-mono"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="text-sm text-muted-foreground">⊕ Step</Label>
              <Input
                value={form.step}
                onChange={(e) => updateForm('step', e.target.value)}
                className="font-mono"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm text-muted-foreground">Grid levels</Label>
              <Input
                value={form.gridLevels}
                onChange={(e) => updateForm('gridLevels', parseInt(e.target.value) || 0)}
                className="font-mono"
              />
            </div>
          </div>

          <Separator />

          {/* Position Limits */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <Label className="text-sm text-muted-foreground">Max. position</Label>
              <span className="font-mono text-sm">+ {form.maxPosition} {baseAsset}</span>
            </div>
            <div className="flex items-center justify-between">
              <Label className="text-sm text-muted-foreground">Max. margin</Label>
              <span className="font-mono text-sm">+ {form.maxMargin} {baseAsset}</span>
            </div>
            <div className="flex items-center justify-between">
              <Label className="text-sm text-muted-foreground">TP order</Label>
              <span className="font-mono text-sm">+ {form.tpOrder} {baseAsset}</span>
            </div>
            <div className="flex items-center justify-between">
              <Label className="text-sm text-muted-foreground">DCA orders (15)</Label>
              <span className="font-mono text-sm">+ {form.dcaOrders} ARB</span>
            </div>
            <div className="flex items-center justify-between">
              <Label className="text-sm text-muted-foreground">Grid orders (15)</Label>
              <span className="font-mono text-sm">+ {form.gridOrders} ARB</span>
            </div>
          </div>

          <Separator />

          {/* Stop Loss */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-red-500">●</span>
                <Label className="text-sm font-medium">Stop Loss</Label>
              </div>
              <Switch
                checked={form.stopLossEnabled}
                onCheckedChange={(checked) => updateForm('stopLossEnabled', checked)}
              />
            </div>

            {form.stopLossEnabled && (
              <>
                <div className="flex items-center justify-between">
                  <Label className="text-sm text-muted-foreground">Total PNL, %</Label>
                  <div className="flex gap-1">
                    <Button
                      variant={form.stopLossType === 'pnl' ? 'secondary' : 'outline'}
                      size="sm"
                      onClick={() => updateForm('stopLossType', 'pnl')}
                    >
                      PNL
                    </Button>
                    <Button
                      variant={form.stopLossType === 'price' ? 'secondary' : 'outline'}
                      size="sm"
                      onClick={() => updateForm('stopLossType', 'price')}
                    >
                      Price
                    </Button>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label className="text-sm text-muted-foreground">Price</Label>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-muted-foreground">Stop</span>
                    <Input
                      value={form.stopLossValue}
                      onChange={(e) => updateForm('stopLossValue', e.target.value)}
                      className="font-mono flex-1"
                    />
                    <span className="text-sm text-muted-foreground">USDC</span>
                  </div>
                </div>
              </>
            )}
          </div>

          <Separator />

          {/* Take Profit */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-green-500">●</span>
                <Label className="text-sm font-medium">Take Profit</Label>
              </div>
              <Switch
                checked={form.takeProfitEnabled}
                onCheckedChange={(checked) => updateForm('takeProfitEnabled', checked)}
              />
            </div>

            {form.takeProfitEnabled && (
              <>
                <div className="flex items-center justify-between">
                  <Label className="text-sm text-muted-foreground">Total PNL, %</Label>
                  <div className="flex gap-1">
                    <Button
                      variant={form.takeProfitType === 'pnl' ? 'secondary' : 'outline'}
                      size="sm"
                      onClick={() => updateForm('takeProfitType', 'pnl')}
                    >
                      PNL
                    </Button>
                    <Button
                      variant={form.takeProfitType === 'price' ? 'secondary' : 'outline'}
                      size="sm"
                      onClick={() => updateForm('takeProfitType', 'price')}
                    >
                      Price
                    </Button>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label className="text-sm text-muted-foreground">Total PNL, %</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      value={form.takeProfitValue}
                      onChange={(e) => updateForm('takeProfitValue', e.target.value)}
                      className="font-mono flex-1"
                    />
                    <span className="text-sm text-muted-foreground">USDC</span>
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Error Display */}
          {error && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-500 text-sm flex items-center gap-2">
              <AlertTriangle className="h-4 w-4" />
              {error}
            </div>
          )}
        </div>

        {/* Action Buttons */}
        <div className="sticky bottom-0 bg-background pt-4 pb-2 border-t space-y-2">
          <Button
            className="w-full"
            onClick={handleSave}
            disabled={isSubmitting}
          >
            {isSubmitting ? 'Saving...' : 'Save Changes'}
          </Button>
          <Button
            variant="outline"
            className="w-full"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}

export default BotModifyDialog
