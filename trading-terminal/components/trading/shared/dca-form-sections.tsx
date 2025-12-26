/**
 * Shared DCA Bot Form Sections
 * 
 * Reusable form sections used by both DCA spot and DCA futures dialogs.
 * These are complete collapsible sections that handle their own state.
 * 
 * @module components/trading/shared/dca-form-sections
 */

'use client'

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import {
  Collapsible,
  CollapsibleContent,
} from '@/components/ui/collapsible'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Slider } from '@/components/ui/slider'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  AlertTriangle,
  Shield,
  Target,
  Info,
  X,
  Loader2,
} from 'lucide-react'
import {
  SectionHeader,
  NumberStepper,
  MultiplierSlider,
  OrderTypeToggle,
  ToggleRow,
  DCAOrderPreview,
} from './dca-form-components'
import type {
  DCAConfig,
  TakeProfitType,
  PriceReference,
  BotStartCondition,
  IndicatorType,
  IndicatorTimeframe,
} from '@/lib/types/bot'
import {
  INDICATOR_TIMEFRAME_LABELS,
  DEFAULT_SIGNAL_CONFIG,
} from '@/lib/types/bot'
import { fetchCombinedIndicatorSignals } from '@/lib/api'

// ============================================================================
// Constants
// ============================================================================

/** Start condition options for the dropdown */
const START_CONDITION_OPTIONS: { value: BotStartCondition; label: string }[] = [
  { value: 'immediately', label: 'Immediately' },
  { value: 'on_signal', label: 'By indicator signal' },
  { value: 'tradingview_webhook', label: 'TradingView webhook' },
  { value: 'on_price', label: 'On price condition' },
]

/** Indicator type options */
const INDICATOR_OPTIONS: { value: IndicatorType; label: string; icon: string }[] = [
  { value: 'rsi', label: 'RSI', icon: '📊' },
  { value: 'stochastic', label: 'Stochastic', icon: '📈' },
  { value: 'macd', label: 'MACD', icon: '𝒇' },
]

/** Timeframe options */
const TIMEFRAME_OPTIONS: { value: IndicatorTimeframe; label: string }[] = [
  { value: '1m', label: '1m' },
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '30m', label: '30m' },
  { value: '1h', label: '1h' },
  { value: '4h', label: '4h' },
  { value: '1d', label: '1d' },
]

/** Take profit price reference options */
const TP_PRICE_REFERENCE_OPTIONS: { value: PriceReference; label: string; hasIndicators: boolean }[] = [
  { value: 'average_price', label: 'Average price', hasIndicators: false },
  { value: 'average_price_indicators', label: 'Average price + indicator', hasIndicators: true },
  { value: 'base_order_price', label: 'Base order price', hasIndicators: false },
  { value: 'base_order_price_indicators', label: 'Base order price + indicator', hasIndicators: true },
]

// ============================================================================
// Averaging Orders Section
// ============================================================================

export interface AveragingOrdersSectionProps {
  /** Whether the section is expanded */
  isOpen: boolean
  /** Toggle callback */
  onOpenChange: (open: boolean) => void
  /** Current DCA config */
  dcaConfig: DCAConfig
  /** Update handler for DCA config fields */
  onConfigUpdate: <K extends keyof DCAConfig>(key: K, value: DCAConfig[K]) => void
  /** Currency symbol for display (e.g., "USD", "USDT") */
  currency?: string
  /** Current price of the asset (for order preview) */
  currentPrice?: number
  /** Base order amount (for order preview) */
  baseOrderAmount?: number
  /** Whether this is a short position */
  isShort?: boolean
  /** Asset class - determines if fractional units are allowed */
  assetClass?: 'crypto' | 'stock' | 'forex' | 'commodity' | 'etf' | 'index'
  /** Trading symbol (e.g., 'AAPL', 'BTC/USD') - required for API preview */
  symbol: string
}

/**
 * Averaging Orders configuration section.
 * Handles safety orders amount, quantity, step, and multipliers.
 * Includes a visual preview of all orders with amounts and average prices.
 */
export function AveragingOrdersSection({
  isOpen,
  onOpenChange,
  dcaConfig,
  onConfigUpdate,
  currency = 'USD',
  currentPrice = 0,
  baseOrderAmount = 0,
  isShort = false,
  assetClass = 'crypto',
  symbol,
}: AveragingOrdersSectionProps) {
  // Handler to fix invalid configuration using API-provided suggested fix
  const handleFixConfig = React.useCallback((newOrdersCount: number, newStepPercent: number) => {
    onConfigUpdate('averagingOrders', {
      ...dcaConfig.averagingOrders!,
      ordersCount: newOrdersCount,
      stepPercent: newStepPercent,
    })
  }, [dcaConfig.averagingOrders, onConfigUpdate])
  return (
    <Collapsible open={isOpen} onOpenChange={onOpenChange}>
      <SectionHeader
        title="Averaging orders"
        isOpen={isOpen}
        onToggle={() => onOpenChange(!isOpen)}
      />
      <CollapsibleContent className="space-y-4 pt-4">
        {/* Averaging orders amount */}
        <div className="space-y-2">
          <Label className="text-xs text-muted-foreground">
            Averaging orders amount, {currency}
          </Label>
          <Input
            type="number"
            min={0}
            step="0.01"
            value={dcaConfig.averagingOrders?.totalAmount || 0}
            onChange={(e) => {
              // Parse and sanitize to prevent leading zeros
              const cleaned = e.target.value.replace(/^0+(?=\d)/, '')
              const val = parseFloat(cleaned) || 0
              onConfigUpdate('averagingOrders', {
                ...dcaConfig.averagingOrders!,
                totalAmount: Math.round(val * 100) / 100,
              })
            }}
            onBlur={(e) => {
              // Ensure clean value on blur
              const val = parseFloat(e.target.value) || 0
              e.target.value = Math.round(val * 100) / 100 + ''
            }}
          />
        </div>

        {/* Orders count */}
        <NumberStepper
          label="Averaging orders quantity"
          value={dcaConfig.averagingOrders?.ordersCount || 4}
          onChange={(v) => onConfigUpdate('averagingOrders', {
            ...dcaConfig.averagingOrders!,
            ordersCount: v,
          })}
          min={1}
          max={100}
          step={1}
        />

        {/* Step percent */}
        <div className="space-y-2">
          <Label className="text-xs text-muted-foreground">Averaging orders step, %</Label>
          <Input
            type="number"
            step="0.01"
            value={dcaConfig.averagingOrders?.stepPercent || 1.99}
            onChange={(e) => onConfigUpdate('averagingOrders', {
              ...dcaConfig.averagingOrders!,
              stepPercent: parseFloat(e.target.value) || 0,
            })}
          />
        </div>

        {/* Active Orders Limit */}
        <ToggleRow
          label="Active Orders Limit"
          checked={dcaConfig.averagingOrders?.activeOrdersLimit || false}
          onCheckedChange={(checked) => onConfigUpdate('averagingOrders', {
            ...dcaConfig.averagingOrders!,
            activeOrdersLimit: checked,
          })}
        />

        {/* Amount Multiplier */}
        <MultiplierSlider
          label="Amount multiplier"
          value={dcaConfig.averagingOrders?.amountMultiplier || 1.3}
          enabled={dcaConfig.averagingOrders?.amountMultiplierEnabled || false}
          onValueChange={(v) => onConfigUpdate('averagingOrders', {
            ...dcaConfig.averagingOrders!,
            amountMultiplier: v,
          })}
          onEnabledChange={(enabled) => onConfigUpdate('averagingOrders', {
            ...dcaConfig.averagingOrders!,
            amountMultiplierEnabled: enabled,
          })}
        />

        {/* Step Multiplier */}
        <MultiplierSlider
          label="Step multiplier"
          value={dcaConfig.averagingOrders?.stepMultiplier || 1.3}
          enabled={dcaConfig.averagingOrders?.stepMultiplierEnabled || false}
          onValueChange={(v) => onConfigUpdate('averagingOrders', {
            ...dcaConfig.averagingOrders!,
            stepMultiplier: v,
          })}
          onEnabledChange={(enabled) => onConfigUpdate('averagingOrders', {
            ...dcaConfig.averagingOrders!,
            stepMultiplierEnabled: enabled,
          })}
        />

        {/* DCA Order Preview Table */}
        <DCAOrderPreview
          symbol={symbol}
          baseOrderAmount={baseOrderAmount}
          averagingOrdersAmount={dcaConfig.averagingOrders?.totalAmount || 0}
          ordersCount={dcaConfig.averagingOrders?.ordersCount || 4}
          stepPercent={dcaConfig.averagingOrders?.stepPercent || 1.99}
          amountMultiplier={dcaConfig.averagingOrders?.amountMultiplier || 1.3}
          amountMultiplierEnabled={dcaConfig.averagingOrders?.amountMultiplierEnabled || false}
          stepMultiplier={dcaConfig.averagingOrders?.stepMultiplier || 1.3}
          stepMultiplierEnabled={dcaConfig.averagingOrders?.stepMultiplierEnabled || false}
          currentPrice={currentPrice}
          currency={currency}
          isShort={isShort}
          onFixConfig={handleFixConfig}
          assetClass={assetClass}
        />
      </CollapsibleContent>
    </Collapsible>
  )
}

// ============================================================================
// Take Profit & Stop Loss Section
// ============================================================================

export interface PositionTpSlSectionProps {
  /** Whether the section is expanded */
  isOpen: boolean
  /** Toggle callback */
  onOpenChange: (open: boolean) => void
  /** Current DCA config */
  dcaConfig: DCAConfig
  /** Update handler for DCA config fields */
  onConfigUpdate: <K extends keyof DCAConfig>(key: K, value: DCAConfig[K]) => void
  /** Estimated PnL to display */
  estimatedPnL: number
  /** Currency for display */
  currency?: string
  /** Leverage multiplier for futures (optional) */
  leverage?: number
  /** Custom liquidation warning component */
  liquidationWarning?: React.ReactNode
  /** Trading symbol for indicator calculations (e.g., "AAPL", "BTC/USD") */
  symbol?: string
}

/**
 * Position Take Profit & Stop Loss configuration section.
 * Handles TP type (regular/trailing), price change, and stop loss settings.
 */
export function PositionTpSlSection({
  isOpen,
  onOpenChange,
  dcaConfig,
  onConfigUpdate,
  estimatedPnL,
  currency = 'USD',
  leverage,
  liquidationWarning,
  symbol,
}: PositionTpSlSectionProps) {
  // Get TP signal config (for indicator-based take profit)
  const tpSignalConfig = dcaConfig.takeProfit?.signalConfig || DEFAULT_SIGNAL_CONFIG
  const tpEnabledIndicators = useMemo(
    () => tpSignalConfig.indicators.filter(i => i.enabled),
    [tpSignalConfig.indicators]
  )
  
  // Check if current price reference uses indicators
  const priceRefUsesIndicators = dcaConfig.takeProfit?.priceReference?.includes('indicators') ?? false
  
  return (
    <Collapsible open={isOpen} onOpenChange={onOpenChange}>
      <SectionHeader
        title="Position TP & SL"
        isOpen={isOpen}
        onToggle={() => onOpenChange(!isOpen)}
        icon={<Target className="h-4 w-4 text-muted-foreground" />}
      />
      <CollapsibleContent className="space-y-4 pt-4">
        {/* Take Profit */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Label className="text-sm font-medium">Take Profit</Label>
            <Switch
              checked={dcaConfig.takeProfit?.enabled ?? true}
              onCheckedChange={(checked) => onConfigUpdate('takeProfit', {
                ...dcaConfig.takeProfit!,
                enabled: checked,
              })}
            />
          </div>

          {dcaConfig.takeProfit?.enabled && (
            <div className="p-3 bg-muted/30 rounded-lg space-y-3">
              {/* Regular/Trailing tabs */}
              <Tabs
                value={dcaConfig.takeProfit?.type || 'regular'}
                onValueChange={(v) => onConfigUpdate('takeProfit', {
                  ...dcaConfig.takeProfit!,
                  type: v as TakeProfitType,
                })}
              >
                <TabsList className="w-full">
                  <TabsTrigger value="regular" className="flex-1">Regular</TabsTrigger>
                  <TabsTrigger value="trailing" className="flex-1">Trailing</TabsTrigger>
                </TabsList>
              </Tabs>

              {/* Price change % */}
              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">
                  Price change, %
                  <Info className="h-3 w-3 ml-1 inline" />
                </Label>
                <Input
                  type="number"
                  step="0.1"
                  value={dcaConfig.takeProfit?.priceChangePercent || 1}
                  onChange={(e) => onConfigUpdate('takeProfit', {
                    ...dcaConfig.takeProfit!,
                    priceChangePercent: parseFloat(e.target.value) || 0,
                  })}
                />
              </div>

              {/* Trailing deviation % (only for trailing type) */}
              {dcaConfig.takeProfit?.type === 'trailing' && (
                <div className="space-y-2">
                  <Label className="text-xs text-muted-foreground">
                    Trailing deviation, %
                    <Info className="h-3 w-3 ml-1 inline" />
                  </Label>
                  <Input
                    type="number"
                    step="0.1"
                    min="0.1"
                    value={dcaConfig.takeProfit?.trailingDeviation || 0.5}
                    onChange={(e) => onConfigUpdate('takeProfit', {
                      ...dcaConfig.takeProfit!,
                      trailingDeviation: parseFloat(e.target.value) || 0.5,
                    })}
                  />
                  <p className="text-xs text-muted-foreground">
                    Stop trails the price by this percentage. Lower values = tighter trailing.
                  </p>
                </div>
              )}

              {/* Percentage of */}
              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">Percentage of</Label>
                <Select
                  value={dcaConfig.takeProfit?.priceReference || 'average_price'}
                  onValueChange={(v) => onConfigUpdate('takeProfit', {
                    ...dcaConfig.takeProfit!,
                    priceReference: v as PriceReference,
                    // Initialize signal config if switching to indicator mode
                    signalConfig: v.includes('indicators')
                      ? dcaConfig.takeProfit?.signalConfig || DEFAULT_SIGNAL_CONFIG
                      : dcaConfig.takeProfit?.signalConfig,
                  })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TP_PRICE_REFERENCE_OPTIONS.map(option => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Indicator Configuration (when using indicator-based price reference) */}
              {priceRefUsesIndicators && (
                <div className="space-y-3 p-3 bg-muted/50 rounded-lg">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Info className="h-3 w-3" />
                    <span>Exit indicators work opposite to entry (e.g., RSI overbought for long TP)</span>
                  </div>
                  
                  {/* Current indicators */}
                  {tpEnabledIndicators.map((indicator, index) => (
                    <div key={`tp-${indicator.type}-${index}`} className="flex items-center gap-2">
                      <div className="flex items-center gap-2 flex-1 p-2 bg-background rounded border">
                        <span className="text-lg">
                          {INDICATOR_OPTIONS.find(o => o.value === indicator.type)?.icon || '📊'}
                        </span>
                        <Select
                          value={indicator.type}
                          onValueChange={(value: IndicatorType) => {
                            const newIndicators = [...tpSignalConfig.indicators]
                            const existingIndex = newIndicators.findIndex(i => i.type === indicator.type && i.enabled)
                            if (existingIndex >= 0) {
                              newIndicators[existingIndex] = { ...newIndicators[existingIndex], type: value }
                            }
                            onConfigUpdate('takeProfit', {
                              ...dcaConfig.takeProfit!,
                              signalConfig: { ...tpSignalConfig, indicators: newIndicators },
                            })
                          }}
                        >
                          <SelectTrigger className="w-[120px] h-8 border-0 bg-transparent">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {INDICATOR_OPTIONS.map(opt => (
                              <SelectItem key={opt.value} value={opt.value}>
                                {opt.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <Select
                          value={indicator.timeframe}
                          onValueChange={(value: IndicatorTimeframe) => {
                            const newIndicators = [...tpSignalConfig.indicators]
                            const existingIndex = newIndicators.findIndex(i => i.type === indicator.type && i.enabled)
                            if (existingIndex >= 0) {
                              newIndicators[existingIndex] = { ...newIndicators[existingIndex], timeframe: value }
                            }
                            onConfigUpdate('takeProfit', {
                              ...dcaConfig.takeProfit!,
                              signalConfig: { ...tpSignalConfig, indicators: newIndicators },
                            })
                          }}
                        >
                          <SelectTrigger className="w-[70px] h-8">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {TIMEFRAME_OPTIONS.map(opt => (
                              <SelectItem key={opt.value} value={opt.value}>
                                {opt.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0"
                        onClick={() => {
                          const newIndicators = tpSignalConfig.indicators.map(i => 
                            i.type === indicator.type ? { ...i, enabled: false } : i
                          )
                          onConfigUpdate('takeProfit', {
                            ...dcaConfig.takeProfit!,
                            signalConfig: { ...tpSignalConfig, indicators: newIndicators },
                          })
                        }}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}

                  {/* Add indicator button */}
                  <Select
                    value=""
                    onValueChange={(value: IndicatorType) => {
                      if (!value) return
                      const newIndicators = tpSignalConfig.indicators.map(i => 
                        i.type === value ? { ...i, enabled: true } : i
                      )
                      // If indicator doesn't exist, add it
                      if (!newIndicators.find(i => i.type === value)) {
                        newIndicators.push({ type: value, timeframe: '1m', enabled: true })
                      }
                      onConfigUpdate('takeProfit', {
                        ...dcaConfig.takeProfit!,
                        signalConfig: { ...tpSignalConfig, indicators: newIndicators },
                      })
                    }}
                  >
                    <SelectTrigger className="w-full bg-primary text-primary-foreground hover:bg-primary/90">
                      <span>Add exit indicator ▾</span>
                    </SelectTrigger>
                    <SelectContent>
                      {INDICATOR_OPTIONS.filter(
                        opt => !tpEnabledIndicators.find(i => i.type === opt.value)
                      ).map(opt => (
                        <SelectItem key={opt.value} value={opt.value}>
                          <span className="flex items-center gap-2">
                            <span>{opt.icon}</span>
                            {opt.label}
                          </span>
                        </SelectItem>
                      ))}
                      {INDICATOR_OPTIONS.filter(
                        opt => !tpEnabledIndicators.find(i => i.type === opt.value)
                      ).length === 0 && (
                        <div className="px-2 py-1.5 text-sm text-muted-foreground">
                          All indicators added
                        </div>
                      )}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Order type toggle */}
              <OrderTypeToggle
                value={dcaConfig.takeProfit?.orderType || 'limit'}
                onChange={(v) => onConfigUpdate('takeProfit', {
                  ...dcaConfig.takeProfit!,
                  orderType: v,
                })}
              />

              {/* PNL Preview */}
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">
                  PNL{leverage ? ` (with ${leverage}x leverage)` : ''}
                </span>
                <span className="text-green-500 font-medium">
                  ≈ +${estimatedPnL.toFixed(2)} {currency}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Stop Loss */}
        <div className="flex items-center justify-between">
          <Label className="text-sm font-medium flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-red-500" />
            Stop Loss
          </Label>
          <Switch
            checked={dcaConfig.stopLoss?.enabled || false}
            onCheckedChange={(checked) => onConfigUpdate('stopLoss', {
              ...dcaConfig.stopLoss!,
              enabled: checked,
            })}
          />
        </div>

        {dcaConfig.stopLoss?.enabled && (
          <div className="p-3 bg-muted/30 rounded-lg space-y-3">
            {/* Stop Loss Price Change % */}
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">
                Price change, %
                <Info className="h-3 w-3 ml-1 inline" />
              </Label>
              <Input
                type="number"
                step="0.1"
                value={dcaConfig.stopLoss?.percent || 5}
                onChange={(e) => onConfigUpdate('stopLoss', {
                  ...dcaConfig.stopLoss!,
                  percent: parseFloat(e.target.value) || 0,
                })}
              />
            </div>

            {/* PNL Preview for Stop Loss */}
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">
                PNL{leverage ? ` (with ${leverage}x leverage)` : ''}
              </span>
              <span className="text-red-500 font-medium">
                ≈ -{((dcaConfig.stopLoss?.percent || 5) * (leverage || 1) / 100 * estimatedPnL * 100 / (dcaConfig.takeProfit?.priceChangePercent || 1)).toFixed(2)} {currency}
              </span>
            </div>

            {/* Trailing Stop Loss Toggle */}
            <div className="flex items-center justify-between pt-2 border-t border-border/50">
              <Label className="text-sm font-medium flex items-center gap-2">
                <Info className="h-4 w-4 text-muted-foreground" />
                Trailing SL
              </Label>
              <Switch
                checked={dcaConfig.stopLoss?.trailingEnabled || false}
                onCheckedChange={(checked) => onConfigUpdate('stopLoss', {
                  ...dcaConfig.stopLoss!,
                  trailingEnabled: checked,
                  trailingDeviationPercent: checked ? (dcaConfig.stopLoss?.trailingDeviationPercent || 1) : undefined,
                })}
              />
            </div>

            {/* Trailing Deviation % (only when trailing is enabled) */}
            {dcaConfig.stopLoss?.trailingEnabled && (
              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">
                  Price deviation, %
                  <Info className="h-3 w-3 ml-1 inline" />
                </Label>
                <Input
                  type="number"
                  step="0.1"
                  min="0.1"
                  value={dcaConfig.stopLoss?.trailingDeviationPercent || 1}
                  onChange={(e) => onConfigUpdate('stopLoss', {
                    ...dcaConfig.stopLoss!,
                    trailingDeviationPercent: parseFloat(e.target.value) || 1,
                  })}
                />
                <p className="text-xs text-muted-foreground">
                  Stop trails the price by this percentage as it moves in your favor.
                </p>
              </div>
            )}

            {liquidationWarning}
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}

// ============================================================================
// Risk Management Section
// ============================================================================

export interface RiskManagementSectionProps {
  /** Whether the section is expanded */
  isOpen: boolean
  /** Toggle callback */
  onOpenChange: (open: boolean) => void
  /** Current DCA config */
  dcaConfig: DCAConfig
  /** Update handler for DCA config fields */
  onConfigUpdate: <K extends keyof DCAConfig>(key: K, value: DCAConfig[K]) => void
  /** Total investment amount for calculating USD values from percentages */
  totalInvestment?: number
  /** Currency for display */
  currency?: string
  /** Current price of the asset for calculating deviations */
  currentPrice?: number
}

/**
 * Risk Management configuration section.
 * Handles pump/dump protection, profit targets, loss limits, and price bounds.
 */
export function RiskManagementSection({
  isOpen,
  onOpenChange,
  dcaConfig,
  onConfigUpdate,
  totalInvestment = 0,
  currency = 'USD',
  currentPrice = 0,
}: RiskManagementSectionProps) {
  return (
    <Collapsible open={isOpen} onOpenChange={onOpenChange}>
      <SectionHeader
        title="Risk management"
        isOpen={isOpen}
        onToggle={() => onOpenChange(!isOpen)}
        icon={<Shield className="h-4 w-4 text-muted-foreground" />}
      />
      <CollapsibleContent className="space-y-4 pt-4">
        {/* Pump/Dump Protection */}
        <ToggleRow
          label="Pump / Dump Protection"
          checked={dcaConfig.riskManagement?.pumpDumpProtection ?? true}
          onCheckedChange={(checked) => onConfigUpdate('riskManagement', {
            ...dcaConfig.riskManagement!,
            pumpDumpProtection: checked,
          })}
        />

        {/* Target Total Profit */}
        <ToggleRow
          label="Target total profit"
          checked={dcaConfig.riskManagement?.targetTotalProfit?.enabled || false}
          onCheckedChange={(checked) => onConfigUpdate('riskManagement', {
            ...dcaConfig.riskManagement!,
            targetTotalProfit: {
              ...dcaConfig.riskManagement?.targetTotalProfit,
              enabled: checked,
              percent: dcaConfig.riskManagement?.targetTotalProfit?.percent ?? 30,
            },
          })}
        />

        {/* Target Total Profit Input - shown when enabled */}
        {dcaConfig.riskManagement?.targetTotalProfit?.enabled && (
          <div className="p-3 bg-muted/30 rounded-lg space-y-3">
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">Investment change, %</Label>
              <Input
                type="number"
                step="0.1"
                min="0"
                value={dcaConfig.riskManagement?.targetTotalProfit?.percent || 30}
                onChange={(e) => onConfigUpdate('riskManagement', {
                  ...dcaConfig.riskManagement!,
                  targetTotalProfit: {
                    ...dcaConfig.riskManagement?.targetTotalProfit,
                    enabled: true,
                    percent: parseFloat(e.target.value) || 0,
                  },
                })}
              />
            </div>
            {totalInvestment > 0 && (
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground"></span>
                <span className="text-green-500 font-medium">
                  ≈ {((dcaConfig.riskManagement?.targetTotalProfit?.percent || 30) / 100 * totalInvestment).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {currency}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Allowed Total Loss */}
        <ToggleRow
          label="Allowed total loss"
          checked={dcaConfig.riskManagement?.allowedTotalLoss?.enabled || false}
          onCheckedChange={(checked) => onConfigUpdate('riskManagement', {
            ...dcaConfig.riskManagement!,
            allowedTotalLoss: {
              ...dcaConfig.riskManagement?.allowedTotalLoss,
              enabled: checked,
              percent: dcaConfig.riskManagement?.allowedTotalLoss?.percent ?? 30,
            },
          })}
        />

        {/* Allowed Total Loss Input - shown when enabled */}
        {dcaConfig.riskManagement?.allowedTotalLoss?.enabled && (
          <div className="p-3 bg-muted/30 rounded-lg space-y-3">
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">Investment change, %</Label>
              <Input
                type="number"
                step="0.1"
                min="0"
                value={dcaConfig.riskManagement?.allowedTotalLoss?.percent || 30}
                onChange={(e) => onConfigUpdate('riskManagement', {
                  ...dcaConfig.riskManagement!,
                  allowedTotalLoss: {
                    ...dcaConfig.riskManagement?.allowedTotalLoss,
                    enabled: true,
                    percent: parseFloat(e.target.value) || 0,
                  },
                })}
              />
            </div>
            {totalInvestment > 0 && (
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground"></span>
                <span className="text-red-500 font-medium">
                  ≈ -{((dcaConfig.riskManagement?.allowedTotalLoss?.percent || 30) / 100 * totalInvestment).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {currency}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Max Price */}
        <ToggleRow
          label="Max. price"
          checked={dcaConfig.riskManagement?.maxPrice?.enabled || false}
          onCheckedChange={(checked) => onConfigUpdate('riskManagement', {
            ...dcaConfig.riskManagement!,
            maxPrice: {
              ...dcaConfig.riskManagement?.maxPrice,
              enabled: checked,
              price: dcaConfig.riskManagement?.maxPrice?.price ?? (currentPrice > 0 ? currentPrice * 1.2 : 0),
            },
          })}
        />

        {/* Max Price Input - shown when enabled */}
        {dcaConfig.riskManagement?.maxPrice?.enabled && (
          <div className="p-3 bg-muted/30 rounded-lg space-y-2">
            <div className="flex items-center gap-2">
              <div className="flex-1 space-y-1">
                <Label className="text-xs text-muted-foreground">Max. price</Label>
                <Input
                  type="number"
                  step="0.00001"
                  min="0"
                  value={dcaConfig.riskManagement?.maxPrice?.price || 0}
                  onChange={(e) => onConfigUpdate('riskManagement', {
                    ...dcaConfig.riskManagement!,
                    maxPrice: {
                      ...dcaConfig.riskManagement?.maxPrice,
                      enabled: true,
                      price: parseFloat(e.target.value) || 0,
                    },
                  })}
                />
              </div>
              <div className="flex flex-col items-end gap-1 pt-5">
                <span className="text-lg text-muted-foreground">↕</span>
              </div>
            </div>
            {currentPrice > 0 && dcaConfig.riskManagement?.maxPrice?.price && (
              <div className="text-right text-sm">
                <span className={((dcaConfig.riskManagement.maxPrice.price - currentPrice) / currentPrice * 100) >= 0 ? 'text-green-500' : 'text-red-500'}>
                  {((dcaConfig.riskManagement.maxPrice.price - currentPrice) / currentPrice * 100) >= 0 ? '+' : ''}
                  {((dcaConfig.riskManagement.maxPrice.price - currentPrice) / currentPrice * 100).toFixed(2)}%
                </span>
              </div>
            )}
          </div>
        )}

        {/* Reserve Funds - placeholder between max and min */}
        <ToggleRow
          label="Reserve funds"
          checked={false}
          onCheckedChange={() => {}}
        />

        {/* Min Price */}
        <ToggleRow
          label="Min. price"
          checked={dcaConfig.riskManagement?.minPrice?.enabled || false}
          onCheckedChange={(checked) => onConfigUpdate('riskManagement', {
            ...dcaConfig.riskManagement!,
            minPrice: {
              ...dcaConfig.riskManagement?.minPrice,
              enabled: checked,
              price: dcaConfig.riskManagement?.minPrice?.price ?? (currentPrice > 0 ? currentPrice * 0.8 : 0),
            },
          })}
        />

        {/* Min Price Input - shown when enabled */}
        {dcaConfig.riskManagement?.minPrice?.enabled && (
          <div className="p-3 bg-muted/30 rounded-lg space-y-2">
            <div className="flex items-center gap-2">
              <div className="flex-1 space-y-1">
                <Label className="text-xs text-muted-foreground">Min. price</Label>
                <Input
                  type="number"
                  step="0.00001"
                  min="0"
                  value={dcaConfig.riskManagement?.minPrice?.price || 0}
                  onChange={(e) => onConfigUpdate('riskManagement', {
                    ...dcaConfig.riskManagement!,
                    minPrice: {
                      ...dcaConfig.riskManagement?.minPrice,
                      enabled: true,
                      price: parseFloat(e.target.value) || 0,
                    },
                  })}
                />
              </div>
              <div className="flex flex-col items-end gap-1 pt-5">
                <span className="text-lg text-muted-foreground">↕</span>
              </div>
            </div>
            {currentPrice > 0 && dcaConfig.riskManagement?.minPrice?.price && (
              <div className="text-right text-sm">
                <span className={((dcaConfig.riskManagement.minPrice.price - currentPrice) / currentPrice * 100) >= 0 ? 'text-green-500' : 'text-red-500'}>
                  {((dcaConfig.riskManagement.minPrice.price - currentPrice) / currentPrice * 100).toFixed(2)}%
                </span>
              </div>
            )}
          </div>
        )}

        {/* Reinvest Profit */}
        <ToggleRow
          label="Reinvest Profit"
          checked={dcaConfig.riskManagement?.reinvestProfit?.enabled || false}
          onCheckedChange={(checked) => onConfigUpdate('riskManagement', {
            ...dcaConfig.riskManagement!,
            reinvestProfit: {
              ...dcaConfig.riskManagement?.reinvestProfit,
              enabled: checked,
              percent: dcaConfig.riskManagement?.reinvestProfit?.percent ?? 100,
            },
          })}
        />
        
        {/* Reinvest Percentage Slider - shown when enabled */}
        {dcaConfig.riskManagement?.reinvestProfit?.enabled && (
          <div className="space-y-2 pl-4 border-l-2 border-primary/20">
            <div className="flex items-center justify-between">
              <Label className="text-sm text-muted-foreground">Reinvest percentage</Label>
              <div className="flex items-center gap-1">
                <Input
                  type="number"
                  min={0}
                  max={100}
                  value={dcaConfig.riskManagement?.reinvestProfit?.percent ?? 100}
                  onChange={(e) => {
                    const val = Math.min(100, Math.max(0, parseInt(e.target.value) || 0))
                    onConfigUpdate('riskManagement', {
                      ...dcaConfig.riskManagement!,
                      reinvestProfit: {
                        ...dcaConfig.riskManagement?.reinvestProfit,
                        enabled: true,
                        percent: val,
                      },
                    })
                  }}
                  className="w-16 h-8 text-center text-sm"
                />
                <span className="text-sm text-muted-foreground">%</span>
              </div>
            </div>
            <Slider
              value={[dcaConfig.riskManagement?.reinvestProfit?.percent ?? 100]}
              onValueChange={(value) => onConfigUpdate('riskManagement', {
                ...dcaConfig.riskManagement!,
                reinvestProfit: {
                  ...dcaConfig.riskManagement?.reinvestProfit,
                  enabled: true,
                  percent: value[0],
                },
              })}
              min={0}
              max={100}
              step={1}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              Percentage of realized profit to reinvest in the next cycle
            </p>
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}

// ============================================================================
// Bot Settings Section
// ============================================================================

export interface BotSettingsSectionProps {
  /** Whether the section is expanded */
  isOpen: boolean
  /** Toggle callback */
  onOpenChange: (open: boolean) => void
  /** Current DCA config */
  dcaConfig: DCAConfig
  /** Update handler for DCA config fields */
  onConfigUpdate: <K extends keyof DCAConfig>(key: K, value: DCAConfig[K]) => void
  /** Default base order amount */
  defaultBaseOrderAmount: number
  /** Currency symbol for display (e.g., "USD", "USDT") */
  currency?: string
  /** Trading symbol for indicator calculations (e.g., "AAPL", "BTC/USD") */
  symbol?: string
  /** Asset class - determines decimal precision */
  assetClass?: 'crypto' | 'stock' | 'forex' | 'commodity' | 'etf' | 'index'
}

/**
 * Bot Settings configuration section.
 * Handles start conditions and base order configuration.
 */
export function BotSettingsSection({
  isOpen,
  onOpenChange,
  dcaConfig,
  onConfigUpdate,
  defaultBaseOrderAmount,
  currency = 'USD',
  symbol,
  assetClass = 'crypto',
}: BotSettingsSectionProps) {
  const startCondition = dcaConfig.startSettings?.startCondition || 'immediately'
  const signalConfig = dcaConfig.startSettings?.signalConfig || DEFAULT_SIGNAL_CONFIG
  
  // Determine decimal precision based on asset class
  const isHighPrecision = assetClass === 'crypto' || assetClass === 'forex'
  const decimalPlaces = isHighPrecision ? 8 : 2
  const inputStep = isHighPrecision ? '0.00000001' : '0.01'
  
  // Memoize enabled indicators to prevent unnecessary re-renders
  const enabledIndicators = useMemo(
    () => signalConfig.indicators.filter(i => i.enabled),
    [signalConfig.indicators]
  )
  
  // Create stable key for indicator config (for dependency tracking)
  const indicatorConfigKey = useMemo(
    () => enabledIndicators.map(i => `${i.type}:${i.timeframe}`).join(','),
    [enabledIndicators]
  )
  
  // State for combined signals from API
  const [combinedSignalsLast30d, setCombinedSignalsLast30d] = useState<number>(0)
  const [isLoadingSignals, setIsLoadingSignals] = useState<boolean>(false)
  const [signalError, setSignalError] = useState<string | null>(null)
  
  // Debounce timer ref for API calls
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null)
  
  // Fetch combined indicator signals (debounced to avoid rapid API calls)
  const fetchIndicatorSignals = useCallback(async () => {
    // Only fetch if we have a symbol and enabled indicators
    if (!symbol || enabledIndicators.length === 0) {
      setCombinedSignalsLast30d(0)
      setSignalError(null)
      return
    }
    
    setIsLoadingSignals(true)
    setSignalError(null)
    
    try {
      const result = await fetchCombinedIndicatorSignals(
        symbol,
        enabledIndicators.map(i => ({
          type: i.type,
          timeframe: i.timeframe,
          enabled: i.enabled,
        })),
        30 // 30 days lookback
      )
      
      if (result) {
        setCombinedSignalsLast30d(result.combinedSignalCount)
      } else {
        // API not available - show estimate
        setCombinedSignalsLast30d(0)
        setSignalError('Indicator data unavailable')
      }
    } catch (error) {
      console.error('Failed to fetch indicator signals:', error)
      setSignalError('Failed to load signals')
      setCombinedSignalsLast30d(0)
    } finally {
      setIsLoadingSignals(false)
    }
  }, [symbol, enabledIndicators])
  
  // Debounced fetch - waits 300ms after last change before calling API
  useEffect(() => {
    if (startCondition !== 'on_signal') {
      return
    }
    
    // Clear any pending timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }
    
    // Set new debounce timer (300ms)
    debounceTimerRef.current = setTimeout(() => {
      fetchIndicatorSignals()
    }, 300)
    
    // Cleanup on unmount or dependency change
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
      }
    }
  }, [startCondition, indicatorConfigKey, symbol, fetchIndicatorSignals])

  return (
    <Collapsible open={isOpen} onOpenChange={onOpenChange}>
      <SectionHeader
        title="Bot settings"
        isOpen={isOpen}
        onToggle={() => onOpenChange(!isOpen)}
      />
      <CollapsibleContent className="space-y-4 pt-4">
        {/* Bot start conditions */}
        <div className="space-y-2">
          <Label className="text-sm text-muted-foreground">Bot start conditions</Label>
          <div className="p-3 bg-muted/30 rounded-lg space-y-4">
            {/* Start Condition Dropdown */}
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">Place base order</Label>
              <Select
                value={startCondition}
                onValueChange={(value: BotStartCondition) => {
                  onConfigUpdate('startSettings', {
                    ...dcaConfig.startSettings!,
                    startCondition: value,
                    // Initialize signal config if switching to indicator mode
                    signalConfig: value === 'on_signal' 
                      ? dcaConfig.startSettings?.signalConfig || DEFAULT_SIGNAL_CONFIG
                      : dcaConfig.startSettings?.signalConfig,
                    // Initialize TradingView config if switching to webhook mode
                    tradingViewConfig: value === 'tradingview_webhook'
                      ? dcaConfig.startSettings?.tradingViewConfig || { enabled: true }
                      : dcaConfig.startSettings?.tradingViewConfig,
                  })
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {START_CONDITION_OPTIONS.map(option => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Indicator Signal Configuration */}
            {startCondition === 'on_signal' && (
              <div className="space-y-3 p-3 bg-muted/50 rounded-lg">
                {/* Current indicators */}
                {enabledIndicators.map((indicator, index) => (
                  <div key={`${indicator.type}-${index}`} className="flex items-center gap-2">
                    <div className="flex items-center gap-2 flex-1 p-2 bg-background rounded border">
                      <span className="text-lg">
                        {INDICATOR_OPTIONS.find(o => o.value === indicator.type)?.icon || '📊'}
                      </span>
                      <Select
                        value={indicator.type}
                        onValueChange={(value: IndicatorType) => {
                          const newIndicators = [...signalConfig.indicators]
                          const existingIndex = newIndicators.findIndex(i => i.type === indicator.type && i.enabled)
                          if (existingIndex >= 0) {
                            newIndicators[existingIndex] = { ...newIndicators[existingIndex], type: value }
                          }
                          onConfigUpdate('startSettings', {
                            ...dcaConfig.startSettings!,
                            signalConfig: { ...signalConfig, indicators: newIndicators },
                          })
                        }}
                      >
                        <SelectTrigger className="w-[120px] h-8 border-0 bg-transparent">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {INDICATOR_OPTIONS.map(opt => (
                            <SelectItem key={opt.value} value={opt.value}>
                              {opt.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Select
                        value={indicator.timeframe}
                        onValueChange={(value: IndicatorTimeframe) => {
                          const newIndicators = [...signalConfig.indicators]
                          const existingIndex = newIndicators.findIndex(i => i.type === indicator.type && i.enabled)
                          if (existingIndex >= 0) {
                            newIndicators[existingIndex] = { ...newIndicators[existingIndex], timeframe: value }
                          }
                          onConfigUpdate('startSettings', {
                            ...dcaConfig.startSettings!,
                            signalConfig: { ...signalConfig, indicators: newIndicators },
                          })
                        }}
                      >
                        <SelectTrigger className="w-[70px] h-8">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {TIMEFRAME_OPTIONS.map(opt => (
                            <SelectItem key={opt.value} value={opt.value}>
                              {opt.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 w-8 p-0"
                      onClick={() => {
                        const newIndicators = signalConfig.indicators.map(i => 
                          i.type === indicator.type ? { ...i, enabled: false } : i
                        )
                        onConfigUpdate('startSettings', {
                          ...dcaConfig.startSettings!,
                          signalConfig: { ...signalConfig, indicators: newIndicators },
                        })
                      }}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ))}

                {/* Combined signals display */}
                {enabledIndicators.length > 0 && (
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Combined signals last 30d</span>
                    <span className="font-medium flex items-center gap-1">
                      {isLoadingSignals ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : signalError ? (
                        <span className="text-muted-foreground text-xs">{signalError}</span>
                      ) : (
                        combinedSignalsLast30d.toLocaleString()
                      )}
                    </span>
                  </div>
                )}

                {/* Add indicator button */}
                <Select
                  value=""
                  onValueChange={(value: IndicatorType) => {
                    if (!value) return
                    const newIndicators = signalConfig.indicators.map(i => 
                      i.type === value ? { ...i, enabled: true } : i
                    )
                    // If indicator doesn't exist, add it
                    if (!newIndicators.find(i => i.type === value)) {
                      newIndicators.push({ type: value, timeframe: '1m', enabled: true })
                    }
                    onConfigUpdate('startSettings', {
                      ...dcaConfig.startSettings!,
                      signalConfig: { ...signalConfig, indicators: newIndicators },
                    })
                  }}
                >
                  <SelectTrigger className="w-full bg-primary text-primary-foreground hover:bg-primary/90">
                    <span>Add indicator ▾</span>
                  </SelectTrigger>
                  <SelectContent>
                    {INDICATOR_OPTIONS.filter(
                      opt => !enabledIndicators.find(i => i.type === opt.value)
                    ).map(opt => (
                      <SelectItem key={opt.value} value={opt.value}>
                        <span className="flex items-center gap-2">
                          <span>{opt.icon}</span>
                          {opt.label}
                        </span>
                      </SelectItem>
                    ))}
                    {INDICATOR_OPTIONS.filter(
                      opt => !enabledIndicators.find(i => i.type === opt.value)
                    ).length === 0 && (
                      <div className="px-2 py-1.5 text-sm text-muted-foreground">
                        All indicators added
                      </div>
                    )}
                  </SelectContent>
                </Select>
              </div>
            )}

            {/* TradingView Webhook Configuration */}
            {startCondition === 'tradingview_webhook' && (
              <div className="space-y-3 p-3 bg-muted/50 rounded-lg">
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-lg">📺</span>
                  <span className="font-medium">TradingView Webhook</span>
                </div>
                <p className="text-xs text-muted-foreground">
                  Bot will wait for a webhook signal from TradingView to place the base order.
                  Configure your TradingView alert to send a webhook to this bot's endpoint.
                </p>
                <div className="space-y-2">
                  <Label className="text-xs text-muted-foreground">Alert message pattern (optional)</Label>
                  <Input
                    placeholder="e.g., BUY_SIGNAL or leave empty for any"
                    value={dcaConfig.startSettings?.tradingViewConfig?.alertMessagePattern || ''}
                    onChange={(e) => onConfigUpdate('startSettings', {
                      ...dcaConfig.startSettings!,
                      tradingViewConfig: {
                        ...dcaConfig.startSettings?.tradingViewConfig,
                        enabled: true,
                        alertMessagePattern: e.target.value,
                      },
                    })}
                  />
                </div>
              </div>
            )}

            {/* Price Condition Configuration */}
            {startCondition === 'on_price' && (
              <div className="space-y-3 p-3 bg-muted/50 rounded-lg">
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground">Condition</Label>
                    <Select
                      value={dcaConfig.startSettings?.priceCondition?.operator || 'below'}
                      onValueChange={(value) => onConfigUpdate('startSettings', {
                        ...dcaConfig.startSettings!,
                        priceCondition: {
                          ...dcaConfig.startSettings?.priceCondition,
                          operator: value as 'above' | 'below' | 'crosses_above' | 'crosses_below',
                          price: dcaConfig.startSettings?.priceCondition?.price || 0,
                        },
                      })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="below">Price below</SelectItem>
                        <SelectItem value="above">Price above</SelectItem>
                        <SelectItem value="crosses_below">Crosses below</SelectItem>
                        <SelectItem value="crosses_above">Crosses above</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground">Target price</Label>
                    <Input
                      type="number"
                      min={0}
                      step="0.01"
                      placeholder="0.00"
                      value={dcaConfig.startSettings?.priceCondition?.price || ''}
                      onChange={(e) => {
                        const cleaned = e.target.value.replace(/^0+(?=\d)/, '')
                        const val = parseFloat(cleaned) || 0
                        onConfigUpdate('startSettings', {
                          ...dcaConfig.startSettings!,
                          priceCondition: {
                            operator: dcaConfig.startSettings?.priceCondition?.operator || 'below',
                            price: Math.round(val * 100) / 100,
                          },
                        })
                      }}
                    />
                  </div>
                </div>
              </div>
            )}
            
            {/* Base order amount */}
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">Base order amount, {currency}</Label>
              <Input
                type="number"
                min={0}
                step={inputStep}
                value={dcaConfig.startSettings?.baseOrderAmount || defaultBaseOrderAmount}
                onChange={(e) => {
                  // Parse and sanitize to prevent leading zeros
                  const cleaned = e.target.value.replace(/^0+(?=\d)/, '')
                  const val = parseFloat(cleaned) || 0
                  // Use appropriate precision based on asset class
                  const multiplier = Math.pow(10, decimalPlaces)
                  onConfigUpdate('startSettings', {
                    ...dcaConfig.startSettings!,
                    baseOrderAmount: Math.round(val * multiplier) / multiplier,
                  })
                }}
                onBlur={(e) => {
                  // Ensure clean value on blur
                  const val = parseFloat(e.target.value) || 0
                  const multiplier = Math.pow(10, decimalPlaces)
                  e.target.value = (Math.round(val * multiplier) / multiplier).toString()
                }}
              />
            </div>

            <OrderTypeToggle
              value={dcaConfig.startSettings?.baseOrderType || 'market'}
              onChange={(v) => onConfigUpdate('startSettings', {
                ...dcaConfig.startSettings!,
                baseOrderType: v,
              })}
            />
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}
