/**
 * DCA Bot Configuration Dialog
 * 
 * Comprehensive configuration dialog for DCA trading bots matching
 * Bitsgap's "Create DCA Bot" interface with collapsible sections for:
 * - Basic settings (exchange, pair, strategy, investment)
 * - Bot settings (start conditions, base order)
 * - Averaging orders (safety orders configuration)
 * - Position TP & SL (take profit and stop loss)
 * - Risk management (protection features)
 * 
 * @module components/trading/dca-bot-config-dialog
 */

'use client'

import React, { useState, useCallback, useMemo, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import {
  ChevronDown,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Info,
  Minus,
  Plus,
  History,
  AlertTriangle,
  Shield,
  Target,
  Wallet,
} from 'lucide-react'
import type {
  BotType,
  PositionMode,
  DCAConfig,
  CreateBotRequest,
  QuickSetupPreset,
  BotOrderType,
  TakeProfitType,
  PriceReference,
  BotStartCondition,
} from '@/lib/types/bot'
import { DEFAULT_DCA_CONFIG, QUICK_SETUP_PRESETS } from '@/lib/types/bot'
import type { AssetClass } from '@/lib/types/asset'

// ============================================================================
// Types
// ============================================================================

interface DCABotConfigDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (request: CreateBotRequest) => Promise<void>
  /** Pre-fill symbol if available */
  initialSymbol?: string
  /** Pre-fill exchange if available */
  initialExchange?: string
  /** Available balance for investment */
  availableBalance?: number
}

interface FormState {
  exchange: string
  symbol: string
  assetClass: AssetClass
  strategy: PositionMode
  investmentAmount: number
  investmentPercent: number
  quickSetup: QuickSetupPreset
  dcaConfig: DCAConfig
}

// ============================================================================
// Constants
// ============================================================================

const EXCHANGES = [
  { value: 'coinbase', label: 'Coinbase' },
  { value: 'alpaca', label: 'Alpaca' },
  { value: 'binance', label: 'Binance' },
  { value: 'kraken', label: 'Kraken' },
]

const ASSET_CLASSES: { value: AssetClass; label: string }[] = [
  { value: 'crypto', label: 'Crypto' },
  { value: 'stock', label: 'Stocks' },
  { value: 'forex', label: 'Forex' },
  { value: 'etf', label: 'ETF' },
]

// ============================================================================
// Sub-components
// ============================================================================

/**
 * Collapsible Section Header
 */
function SectionHeader({
  title,
  isOpen,
  onToggle,
  icon,
}: {
  title: string
  isOpen: boolean
  onToggle: () => void
  icon?: React.ReactNode
}) {
  return (
    <CollapsibleTrigger
      onClick={onToggle}
      className="flex items-center justify-between w-full py-3 hover:bg-muted/50 rounded-lg px-2 -mx-2 transition-colors"
    >
      <div className="flex items-center gap-2">
        {icon}
        <span className="font-medium">{title}</span>
      </div>
      {isOpen ? (
        <ChevronDown className="h-4 w-4 text-muted-foreground" />
      ) : (
        <ChevronRight className="h-4 w-4 text-muted-foreground" />
      )}
    </CollapsibleTrigger>
  )
}

/**
 * Number Input with +/- buttons
 */
function NumberStepper({
  value,
  onChange,
  min = 0,
  max = 100,
  step = 1,
  label,
  suffix,
}: {
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  step?: number
  label?: string
  suffix?: string
}) {
  const decrement = () => onChange(Math.max(min, value - step))
  const increment = () => onChange(Math.min(max, value + step))

  return (
    <div className="space-y-2">
      {label && <Label className="text-sm text-muted-foreground">{label}</Label>}
      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8"
          onClick={decrement}
          disabled={value <= min}
        >
          <Minus className="h-3 w-3" />
        </Button>
        <div className="flex-1 text-center">
          <span className="text-lg font-semibold">{value}</span>
          {suffix && <span className="text-sm text-muted-foreground ml-1">{suffix}</span>}
        </div>
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8"
          onClick={increment}
          disabled={value >= max}
        >
          <Plus className="h-3 w-3" />
        </Button>
      </div>
    </div>
  )
}

/**
 * Multiplier Slider with toggle
 */
function MultiplierSlider({
  label,
  value,
  enabled,
  onValueChange,
  onEnabledChange,
  min = 1,
  max = 3,
  step = 0.1,
}: {
  label: string
  value: number
  enabled: boolean
  onValueChange: (value: number) => void
  onEnabledChange: (enabled: boolean) => void
  min?: number
  max?: number
  step?: number
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label className="text-sm">{label}</Label>
        <Switch checked={enabled} onCheckedChange={onEnabledChange} />
      </div>
      {enabled && (
        <div className="flex items-center gap-4">
          <span className="text-sm text-muted-foreground">Off</span>
          <Slider
            value={[value]}
            onValueChange={([v]) => onValueChange(v)}
            min={min}
            max={max}
            step={step}
            className="flex-1"
          />
          <span className="text-sm font-medium min-w-[3rem] text-right">x{value.toFixed(1)}</span>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function DCABotConfigDialog({
  open,
  onOpenChange,
  onSubmit,
  initialSymbol = '',
  initialExchange = 'coinbase',
  availableBalance = 10000,
}: DCABotConfigDialogProps) {
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  // Section collapse states
  const [botSettingsOpen, setBotSettingsOpen] = useState(false)
  const [averagingOrdersOpen, setAveragingOrdersOpen] = useState(true)
  const [positionTpSlOpen, setPositionTpSlOpen] = useState(false)
  const [riskManagementOpen, setRiskManagementOpen] = useState(false)

  const [form, setForm] = useState<FormState>({
    exchange: initialExchange,
    symbol: initialSymbol,
    assetClass: 'crypto',
    strategy: 'long',
    investmentAmount: Math.min(1000, availableBalance),
    investmentPercent: Math.min(10, (1000 / availableBalance) * 100),
    quickSetup: 'mid_term',
    dcaConfig: { ...DEFAULT_DCA_CONFIG },
  })

  // Calculate investment based on percentage
  const handleInvestmentPercentChange = useCallback((percent: number[]) => {
    const newPercent = percent[0]
    const newAmount = (availableBalance * newPercent) / 100
    setForm(prev => ({
      ...prev,
      investmentPercent: newPercent,
      investmentAmount: Math.round(newAmount * 100) / 100,
    }))
  }, [availableBalance])

  // Update form field
  const updateForm = useCallback(<K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm(prev => ({ ...prev, [key]: value }))
    setError(null)
  }, [])

  // Update DCA config nested field
  const updateDcaConfig = useCallback(<K extends keyof DCAConfig>(key: K, value: DCAConfig[K]) => {
    setForm(prev => ({
      ...prev,
      dcaConfig: { ...prev.dcaConfig, [key]: value },
    }))
  }, [])

  // Apply quick setup preset
  const applyQuickSetup = useCallback((preset: QuickSetupPreset) => {
    updateForm('quickSetup', preset)
    if (preset !== 'custom') {
      const presetConfig = QUICK_SETUP_PRESETS[preset]
      setForm(prev => ({
        ...prev,
        quickSetup: preset,
        dcaConfig: {
          ...prev.dcaConfig,
          ...presetConfig,
          averagingOrders: {
            ...prev.dcaConfig.averagingOrders!,
            ...presetConfig.averagingOrders,
          },
          takeProfit: {
            ...prev.dcaConfig.takeProfit!,
            ...presetConfig.takeProfit,
          },
        },
      }))
    }
  }, [updateForm])

  // Calculate estimated PnL
  const estimatedPnL = useMemo(() => {
    const tp = form.dcaConfig.takeProfit?.priceChangePercent || form.dcaConfig.takeProfitPercent
    const amount = form.investmentAmount + (form.dcaConfig.averagingOrders?.totalAmount || 0)
    return (amount * tp) / 100
  }, [form.investmentAmount, form.dcaConfig])

  // Handle submit
  const handleSubmit = async () => {
    if (!form.symbol.trim()) {
      setError('Symbol is required')
      return
    }
    if (form.investmentAmount <= 0) {
      setError('Investment amount must be greater than 0')
      return
    }

    setIsSubmitting(true)
    setError(null)

    try {
      const totalInvestment = form.investmentAmount + 
        (form.dcaConfig.averagingOrders?.totalAmount || 0)
      
      await onSubmit({
        name: `DCA ${form.symbol}`,
        symbol: form.symbol.trim().toUpperCase(),
        exchange: form.exchange,
        botType: 'dca',
        assetClass: form.assetClass,
        positionMode: form.strategy,
        investmentAmount: totalInvestment,
        dcaConfig: form.dcaConfig,
      })
      handleClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create bot')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleClose = () => {
    onOpenChange(false)
    setTimeout(() => {
      setError(null)
      setForm({
        exchange: initialExchange,
        symbol: '',
        assetClass: 'crypto',
        strategy: 'long',
        investmentAmount: Math.min(1000, availableBalance),
        investmentPercent: Math.min(10, (1000 / availableBalance) * 100),
        quickSetup: 'mid_term',
        dcaConfig: { ...DEFAULT_DCA_CONFIG },
      })
    }, 200)
  }

  // Total investment display
  const totalInvestment = form.investmentAmount + (form.dcaConfig.averagingOrders?.totalAmount || 0)

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-md max-h-[90vh] overflow-hidden flex flex-col p-0">
        {/* Header */}
        <DialogHeader className="flex-shrink-0 px-6 pt-6 pb-4 border-b">
          <DialogTitle className="flex items-center gap-2">
            Create DCA Bot
            <Info className="h-4 w-4 text-muted-foreground cursor-help" />
          </DialogTitle>
        </DialogHeader>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
          {/* Exchange & Pair Selection */}
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground uppercase">Exchange</Label>
              <Select value={form.exchange} onValueChange={(v) => updateForm('exchange', v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {EXCHANGES.map(ex => (
                    <SelectItem key={ex.value} value={ex.value}>{ex.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground uppercase">Pair</Label>
              <Input
                placeholder="TAO / USD"
                value={form.symbol}
                onChange={(e) => updateForm('symbol', e.target.value.toUpperCase())}
              />
            </div>

            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground uppercase">Asset Type</Label>
              <Select 
                value={form.assetClass} 
                onValueChange={(v) => updateForm('assetClass', v as AssetClass)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ASSET_CLASSES.map(ac => (
                    <SelectItem key={ac.value} value={ac.value}>{ac.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Strategy Toggle */}
          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground uppercase flex items-center gap-1">
              Strategy
              <Info className="h-3 w-3" />
            </Label>
            <div className="flex rounded-lg border p-1">
              <Button
                variant={form.strategy === 'long' ? 'default' : 'ghost'}
                className={cn(
                  'flex-1',
                  form.strategy === 'long' && 'bg-primary text-primary-foreground'
                )}
                onClick={() => updateForm('strategy', 'long')}
              >
                Long
              </Button>
              <Button
                variant={form.strategy === 'short' ? 'default' : 'ghost'}
                className={cn(
                  'flex-1',
                  form.strategy === 'short' && 'bg-red-600 hover:bg-red-700 text-white'
                )}
                onClick={() => updateForm('strategy', 'short')}
              >
                Short
              </Button>
            </div>
          </div>

          {/* Investment Amount */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-xs text-muted-foreground uppercase">
                Investment, {form.symbol.split('/')[0] || 'USD'}
              </Label>
              <span className="text-xs text-muted-foreground">
                ≈ ${availableBalance.toLocaleString()} USD
              </span>
            </div>
            
            <div className="flex items-center gap-3">
              <Input
                type="number"
                value={form.investmentAmount}
                onChange={(e) => {
                  const val = parseFloat(e.target.value) || 0
                  updateForm('investmentAmount', val)
                  updateForm('investmentPercent', (val / availableBalance) * 100)
                }}
                className="flex-1"
              />
              <Badge variant="outline" className="px-3 py-2">
                {form.investmentPercent.toFixed(0)}%
              </Badge>
            </div>

            <Slider
              value={[form.investmentPercent]}
              onValueChange={handleInvestmentPercentChange}
              max={100}
              step={1}
              className="mt-2"
            />
          </div>

          {/* Quick Setup */}
          <div className="space-y-3">
            <Label className="text-xs text-muted-foreground uppercase flex items-center gap-1">
              Quick Setup
              <Info className="h-3 w-3" />
            </Label>
            <div className="flex gap-2">
              {(['short_term', 'mid_term', 'long_term'] as QuickSetupPreset[]).map((preset) => (
                <Button
                  key={preset}
                  variant={form.quickSetup === preset ? 'default' : 'outline'}
                  size="sm"
                  className="flex-1"
                  onClick={() => applyQuickSetup(preset)}
                >
                  {preset.replace('_', '-').replace(/^\w/, c => c.toUpperCase()).replace('-t', '-T')}
                </Button>
              ))}
            </div>
            <Button
              variant="link"
              className="text-primary p-0 h-auto text-sm"
              onClick={() => applyQuickSetup('custom')}
            >
              Manual adjustment →
            </Button>
          </div>

          <Separator />

          {/* Bot Settings Section */}
          <Collapsible open={botSettingsOpen} onOpenChange={setBotSettingsOpen}>
            <SectionHeader
              title="Bot settings"
              isOpen={botSettingsOpen}
              onToggle={() => setBotSettingsOpen(!botSettingsOpen)}
            />
            <CollapsibleContent className="space-y-4 pt-4">
              {/* Bot start conditions */}
              <div className="space-y-2">
                <Label className="text-sm text-muted-foreground">Bot start conditions</Label>
                <div className="p-3 bg-muted/30 rounded-lg space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm">Place base order</span>
                    <Badge variant="secondary">Immediately</Badge>
                  </div>
                  
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground">Base order amount</Label>
                    <Input
                      type="number"
                      value={form.dcaConfig.startSettings?.baseOrderAmount || form.investmentAmount * 0.2}
                      onChange={(e) => updateDcaConfig('startSettings', {
                        ...form.dcaConfig.startSettings!,
                        baseOrderAmount: parseFloat(e.target.value) || 0,
                      })}
                    />
                  </div>

                  <div className="flex rounded-lg border p-1">
                    <Button
                      variant={form.dcaConfig.startSettings?.baseOrderType === 'limit' ? 'default' : 'ghost'}
                      size="sm"
                      className="flex-1"
                      onClick={() => updateDcaConfig('startSettings', {
                        ...form.dcaConfig.startSettings!,
                        baseOrderType: 'limit',
                      })}
                    >
                      Limit
                    </Button>
                    <Button
                      variant={form.dcaConfig.startSettings?.baseOrderType === 'market' ? 'default' : 'ghost'}
                      size="sm"
                      className="flex-1"
                      onClick={() => updateDcaConfig('startSettings', {
                        ...form.dcaConfig.startSettings!,
                        baseOrderType: 'market',
                      })}
                    >
                      Market
                    </Button>
                  </div>
                </div>
              </div>
            </CollapsibleContent>
          </Collapsible>

          <Separator />

          {/* Averaging Orders Section */}
          <Collapsible open={averagingOrdersOpen} onOpenChange={setAveragingOrdersOpen}>
            <SectionHeader
              title="Averaging orders"
              isOpen={averagingOrdersOpen}
              onToggle={() => setAveragingOrdersOpen(!averagingOrdersOpen)}
            />
            <CollapsibleContent className="space-y-4 pt-4">
              {/* Averaging orders amount */}
              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">
                  Averaging orders amount, {form.symbol.split('/')[0] || 'USD'}
                </Label>
                <Input
                  type="number"
                  value={form.dcaConfig.averagingOrders?.totalAmount || 0}
                  onChange={(e) => updateDcaConfig('averagingOrders', {
                    ...form.dcaConfig.averagingOrders!,
                    totalAmount: parseFloat(e.target.value) || 0,
                  })}
                />
              </div>

              {/* Orders count */}
              <NumberStepper
                label="Averaging orders quantity"
                value={form.dcaConfig.averagingOrders?.ordersCount || 4}
                onChange={(v) => updateDcaConfig('averagingOrders', {
                  ...form.dcaConfig.averagingOrders!,
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
                  value={form.dcaConfig.averagingOrders?.stepPercent || 1.99}
                  onChange={(e) => updateDcaConfig('averagingOrders', {
                    ...form.dcaConfig.averagingOrders!,
                    stepPercent: parseFloat(e.target.value) || 0,
                  })}
                />
              </div>

              {/* Active Orders Limit */}
              <div className="flex items-center justify-between">
                <Label className="text-sm">Active Orders Limit</Label>
                <Switch
                  checked={form.dcaConfig.averagingOrders?.activeOrdersLimit || false}
                  onCheckedChange={(checked) => updateDcaConfig('averagingOrders', {
                    ...form.dcaConfig.averagingOrders!,
                    activeOrdersLimit: checked,
                  })}
                />
              </div>

              {/* Amount Multiplier */}
              <MultiplierSlider
                label="Amount multiplier"
                value={form.dcaConfig.averagingOrders?.amountMultiplier || 1.3}
                enabled={form.dcaConfig.averagingOrders?.amountMultiplierEnabled || false}
                onValueChange={(v) => updateDcaConfig('averagingOrders', {
                  ...form.dcaConfig.averagingOrders!,
                  amountMultiplier: v,
                })}
                onEnabledChange={(enabled) => updateDcaConfig('averagingOrders', {
                  ...form.dcaConfig.averagingOrders!,
                  amountMultiplierEnabled: enabled,
                })}
              />

              {/* Step Multiplier */}
              <MultiplierSlider
                label="Step multiplier"
                value={form.dcaConfig.averagingOrders?.stepMultiplier || 1.3}
                enabled={form.dcaConfig.averagingOrders?.stepMultiplierEnabled || false}
                onValueChange={(v) => updateDcaConfig('averagingOrders', {
                  ...form.dcaConfig.averagingOrders!,
                  stepMultiplier: v,
                })}
                onEnabledChange={(enabled) => updateDcaConfig('averagingOrders', {
                  ...form.dcaConfig.averagingOrders!,
                  stepMultiplierEnabled: enabled,
                })}
              />
            </CollapsibleContent>
          </Collapsible>

          <Separator />

          {/* Position TP & SL Section */}
          <Collapsible open={positionTpSlOpen} onOpenChange={setPositionTpSlOpen}>
            <SectionHeader
              title="Position TP & SL"
              isOpen={positionTpSlOpen}
              onToggle={() => setPositionTpSlOpen(!positionTpSlOpen)}
              icon={<Target className="h-4 w-4 text-muted-foreground" />}
            />
            <CollapsibleContent className="space-y-4 pt-4">
              {/* Take Profit */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label className="text-sm font-medium">Take Profit</Label>
                  <Switch
                    checked={form.dcaConfig.takeProfit?.enabled ?? true}
                    onCheckedChange={(checked) => updateDcaConfig('takeProfit', {
                      ...form.dcaConfig.takeProfit!,
                      enabled: checked,
                    })}
                  />
                </div>

                {form.dcaConfig.takeProfit?.enabled && (
                  <div className="p-3 bg-muted/30 rounded-lg space-y-3">
                    {/* Regular/Trailing tabs */}
                    <Tabs
                      value={form.dcaConfig.takeProfit?.type || 'regular'}
                      onValueChange={(v) => updateDcaConfig('takeProfit', {
                        ...form.dcaConfig.takeProfit!,
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
                        value={form.dcaConfig.takeProfit?.priceChangePercent || 1}
                        onChange={(e) => updateDcaConfig('takeProfit', {
                          ...form.dcaConfig.takeProfit!,
                          priceChangePercent: parseFloat(e.target.value) || 0,
                        })}
                      />
                    </div>

                    {/* Percentage of */}
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">Percentage of</Label>
                      <Select
                        value={form.dcaConfig.takeProfit?.priceReference || 'average_price'}
                        onValueChange={(v) => updateDcaConfig('takeProfit', {
                          ...form.dcaConfig.takeProfit!,
                          priceReference: v as PriceReference,
                        })}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="average_price">Average price</SelectItem>
                          <SelectItem value="base_order_price">Base order price</SelectItem>
                          <SelectItem value="last_order_price">Last order price</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    {/* Limit/Market toggle */}
                    <div className="flex rounded-lg border p-1">
                      <Button
                        variant={form.dcaConfig.takeProfit?.orderType === 'limit' ? 'default' : 'ghost'}
                        size="sm"
                        className="flex-1"
                        onClick={() => updateDcaConfig('takeProfit', {
                          ...form.dcaConfig.takeProfit!,
                          orderType: 'limit',
                        })}
                      >
                        Limit
                      </Button>
                      <Button
                        variant={form.dcaConfig.takeProfit?.orderType === 'market' ? 'default' : 'ghost'}
                        size="sm"
                        className="flex-1"
                        onClick={() => updateDcaConfig('takeProfit', {
                          ...form.dcaConfig.takeProfit!,
                          orderType: 'market',
                        })}
                      >
                        Market
                      </Button>
                    </div>

                    {/* PNL Preview */}
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">PNL</span>
                      <span className="text-green-500 font-medium">
                        ≈ +${estimatedPnL.toFixed(2)} {form.symbol.split('/')[0] || 'USD'}
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
                  checked={form.dcaConfig.stopLoss?.enabled || false}
                  onCheckedChange={(checked) => updateDcaConfig('stopLoss', {
                    ...form.dcaConfig.stopLoss!,
                    enabled: checked,
                  })}
                />
              </div>

              {form.dcaConfig.stopLoss?.enabled && (
                <div className="p-3 bg-muted/30 rounded-lg space-y-3">
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground">Stop Loss, %</Label>
                    <Input
                      type="number"
                      step="0.1"
                      value={form.dcaConfig.stopLoss?.percent || 5}
                      onChange={(e) => updateDcaConfig('stopLoss', {
                        ...form.dcaConfig.stopLoss!,
                        percent: parseFloat(e.target.value) || 0,
                      })}
                    />
                  </div>
                </div>
              )}
            </CollapsibleContent>
          </Collapsible>

          <Separator />

          {/* Risk Management Section */}
          <Collapsible open={riskManagementOpen} onOpenChange={setRiskManagementOpen}>
            <SectionHeader
              title="Risk management"
              isOpen={riskManagementOpen}
              onToggle={() => setRiskManagementOpen(!riskManagementOpen)}
              icon={<Shield className="h-4 w-4 text-muted-foreground" />}
            />
            <CollapsibleContent className="space-y-4 pt-4">
              {/* Pump/Dump Protection */}
              <div className="flex items-center justify-between">
                <Label className="text-sm">Pump / Dump Protection</Label>
                <Switch
                  checked={form.dcaConfig.riskManagement?.pumpDumpProtection || true}
                  onCheckedChange={(checked) => updateDcaConfig('riskManagement', {
                    ...form.dcaConfig.riskManagement!,
                    pumpDumpProtection: checked,
                  })}
                />
              </div>

              {/* Target Total Profit */}
              <div className="flex items-center justify-between">
                <Label className="text-sm">Target total profit</Label>
                <Switch
                  checked={form.dcaConfig.riskManagement?.targetTotalProfit?.enabled || false}
                  onCheckedChange={(checked) => updateDcaConfig('riskManagement', {
                    ...form.dcaConfig.riskManagement!,
                    targetTotalProfit: {
                      ...form.dcaConfig.riskManagement?.targetTotalProfit,
                      enabled: checked,
                    },
                  })}
                />
              </div>

              {/* Allowed Total Loss */}
              <div className="flex items-center justify-between">
                <Label className="text-sm">Allowed total loss</Label>
                <Switch
                  checked={form.dcaConfig.riskManagement?.allowedTotalLoss?.enabled || false}
                  onCheckedChange={(checked) => updateDcaConfig('riskManagement', {
                    ...form.dcaConfig.riskManagement!,
                    allowedTotalLoss: {
                      ...form.dcaConfig.riskManagement?.allowedTotalLoss,
                      enabled: checked,
                    },
                  })}
                />
              </div>

              {/* Max Price */}
              <div className="flex items-center justify-between">
                <Label className="text-sm">Max. price</Label>
                <Switch
                  checked={form.dcaConfig.riskManagement?.maxPrice?.enabled || false}
                  onCheckedChange={(checked) => updateDcaConfig('riskManagement', {
                    ...form.dcaConfig.riskManagement!,
                    maxPrice: {
                      ...form.dcaConfig.riskManagement?.maxPrice,
                      enabled: checked,
                    },
                  })}
                />
              </div>

              {/* Min Price */}
              <div className="flex items-center justify-between">
                <Label className="text-sm">Min. price</Label>
                <Switch
                  checked={form.dcaConfig.riskManagement?.minPrice?.enabled || false}
                  onCheckedChange={(checked) => updateDcaConfig('riskManagement', {
                    ...form.dcaConfig.riskManagement!,
                    minPrice: {
                      ...form.dcaConfig.riskManagement?.minPrice,
                      enabled: checked,
                    },
                  })}
                />
              </div>

              {/* Renewal Profit */}
              <div className="flex items-center justify-between">
                <Label className="text-sm">Renewal profit</Label>
                <Switch
                  checked={form.dcaConfig.riskManagement?.renewalProfit?.enabled || false}
                  onCheckedChange={(checked) => updateDcaConfig('riskManagement', {
                    ...form.dcaConfig.riskManagement!,
                    renewalProfit: {
                      ...form.dcaConfig.riskManagement?.renewalProfit,
                      enabled: checked,
                    },
                  })}
                />
              </div>
            </CollapsibleContent>
          </Collapsible>

          {/* Available Balance */}
          <div className="flex items-center justify-between text-sm p-3 bg-muted/30 rounded-lg">
            <span className="text-muted-foreground">Available for bot use</span>
            <span className="font-medium">
              ${(availableBalance - totalInvestment).toLocaleString()} USD
            </span>
          </div>

          {/* Error Display */}
          {error && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-500 text-sm">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <DialogFooter className="flex-shrink-0 px-6 py-4 border-t">
          <div className="flex items-center justify-between w-full gap-4">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="gap-1">
                <History className="h-3 w-3" />
                30d
              </Badge>
              <Button variant="outline" size="sm">
                Backtest
              </Button>
            </div>
            <Button 
              onClick={handleSubmit} 
              disabled={isSubmitting}
              className="min-w-[120px]"
            >
              {isSubmitting ? 'Creating...' : 'Continue'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default DCABotConfigDialog
