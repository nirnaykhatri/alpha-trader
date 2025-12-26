/**
 * DCA Futures Bot Configuration Dialog
 * 
 * Comprehensive configuration dialog for DCA futures/perpetual trading bots.
 * Extends the spot DCA interface with futures-specific settings:
 * - Leverage selection (1x to 10x)
 * - Margin mode (Cross/Isolated)
 * - Liquidation price preview
 * 
 * Based on Bitsgap's "Create DCA Futures Bot" interface.
 * 
 * @module components/trading/dca-futures-bot-config-dialog
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
} from '@/components/ui/collapsible'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import {
  TrendingUp,
  TrendingDown,
  Info,
  Minus,
  Plus,
  History,
  AlertTriangle,
  Layers,
  Gauge,
} from 'lucide-react'
import type {
  PositionMode,
  DCAConfig,
  CreateBotRequest,
  QuickSetupPreset,
  MarginMode,
} from '@/lib/types/bot'
import { DEFAULT_DCA_CONFIG, QUICK_SETUP_PRESETS } from '@/lib/types/bot'
import type { AssetClass } from '@/lib/types/asset'
import { fetchQuote } from '@/lib/api'

// Import shared components
import {
  SectionHeader,
  AveragingOrdersSection,
  PositionTpSlSection,
  RiskManagementSection,
  BotSettingsSection,
} from './shared'

// ============================================================================
// Types
// ============================================================================

interface DCAFuturesBotConfigDialogProps {
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
  // Futures-specific fields
  leverage: number
  marginMode: MarginMode
}

// ============================================================================
// Constants
// ============================================================================

/** Minimum leverage supported */
const MIN_LEVERAGE = 1

/** Maximum leverage supported */
const MAX_LEVERAGE = 10

/** Default leverage for new bots */
const DEFAULT_LEVERAGE = 1

/** Default margin mode for new bots */
const DEFAULT_MARGIN_MODE: MarginMode = 'isolated'

const FUTURES_EXCHANGES = [
  { value: 'binance_futures', label: 'Binance Futures' },
  { value: 'bitget_futures', label: 'Bitget Futures' },
  { value: 'bybit', label: 'Bybit' },
  { value: 'okx', label: 'OKX' },
]

const ASSET_CLASSES: { value: AssetClass; label: string }[] = [
  { value: 'crypto', label: 'Crypto' },
]

/** Margin mode descriptions for user education */
const MARGIN_MODE_INFO = {
  cross: {
    title: 'Cross Margin',
    description: 'Share your margin balance across all open positions to avoid liquidation. In case of liquidation, you risk losing your full margin balance along with all remaining open positions.',
    risk: 'Higher risk to total balance',
  },
  isolated: {
    title: 'Isolated Margin',
    description: 'Limit your risk to the margin used for this specific position. In case of liquidation, only the margin for this position will be lost.',
    risk: 'Limited risk to position margin',
  },
} as const

// ============================================================================
// Futures-Specific Sub-components
// ============================================================================

/**
 * Leverage Selector with Slider and +/- buttons
 */
function LeverageSelector({
  value,
  onChange,
  investmentAmount,
}: {
  value: number
  onChange: (value: number) => void
  investmentAmount: number
}) {
  const maxPositionValue = investmentAmount * value

  return (
    <div className="space-y-4 p-4 bg-muted/30 rounded-lg border">
      <div className="flex items-center justify-between">
        <Label className="text-sm font-medium flex items-center gap-2">
          <Gauge className="h-4 w-4" />
          Leverage
        </Label>
        <Badge variant="outline" className="text-lg font-bold px-3 py-1">
          {value}x
        </Badge>
      </div>

      {/* Leverage Stepper */}
      <div className="flex items-center gap-3">
        <Button
          variant="outline"
          size="icon"
          className="h-10 w-10"
          onClick={() => onChange(Math.max(MIN_LEVERAGE, value - 1))}
          disabled={value <= MIN_LEVERAGE}
        >
          <Minus className="h-4 w-4" />
        </Button>
        <Slider
          value={[value]}
          onValueChange={([v]) => onChange(v)}
          min={MIN_LEVERAGE}
          max={MAX_LEVERAGE}
          step={1}
          className="flex-1"
        />
        <Button
          variant="outline"
          size="icon"
          className="h-10 w-10"
          onClick={() => onChange(Math.min(MAX_LEVERAGE, value + 1))}
          disabled={value >= MAX_LEVERAGE}
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>

      {/* Leverage tick marks */}
      <div className="flex justify-between text-xs text-muted-foreground px-1">
        {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((tick) => (
          <span
            key={tick}
            className={cn(
              'cursor-pointer hover:text-foreground transition-colors',
              tick === value && 'text-primary font-bold'
            )}
            onClick={() => onChange(tick)}
          >
            {tick}x
          </span>
        ))}
      </div>

      {/* Max Position Value */}
      <div className="flex items-center justify-between pt-2 border-t">
        <span className="text-sm text-muted-foreground">Max position value</span>
        <span className="text-lg font-semibold text-primary">
          {maxPositionValue.toLocaleString('en-US', {
            style: 'currency',
            currency: 'USD',
            minimumFractionDigits: 2,
          })}
        </span>
      </div>

      {/* Leverage Warning */}
      {value >= 5 && (
        <div className="flex items-start gap-2 p-2 bg-yellow-500/10 border border-yellow-500/20 rounded-md">
          <AlertTriangle className="h-4 w-4 text-yellow-500 mt-0.5 flex-shrink-0" />
          <span className="text-xs text-yellow-600 dark:text-yellow-400">
            Higher leverage increases both potential profit and liquidation risk.
            Use with caution.
          </span>
        </div>
      )}
    </div>
  )
}

/**
 * Margin Mode Selector with explanation
 */
function MarginModeSelector({
  value,
  onChange,
}: {
  value: MarginMode
  onChange: (value: MarginMode) => void
}) {
  return (
    <div className="space-y-3 p-4 bg-muted/30 rounded-lg border">
      <div className="flex items-center gap-2">
        <Layers className="h-4 w-4" />
        <Label className="text-sm font-medium">Margin Mode</Label>
      </div>

      <div className="space-y-2">
        {/* Cross Margin Option */}
        <button
          type="button"
          onClick={() => onChange('cross')}
          className={cn(
            'w-full p-3 rounded-lg border text-left transition-all',
            value === 'cross'
              ? 'border-primary bg-primary/5 ring-1 ring-primary'
              : 'border-border hover:border-muted-foreground/50'
          )}
        >
          <div className="flex items-center justify-between mb-1">
            <span className="font-medium">{MARGIN_MODE_INFO.cross.title}</span>
            {value === 'cross' && (
              <Badge variant="default" className="text-xs">Selected</Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            {MARGIN_MODE_INFO.cross.description}
          </p>
        </button>

        {/* Isolated Margin Option */}
        <button
          type="button"
          onClick={() => onChange('isolated')}
          className={cn(
            'w-full p-3 rounded-lg border text-left transition-all',
            value === 'isolated'
              ? 'border-primary bg-primary/5 ring-1 ring-primary'
              : 'border-border hover:border-muted-foreground/50'
          )}
        >
          <div className="flex items-center justify-between mb-1">
            <span className="font-medium">{MARGIN_MODE_INFO.isolated.title}</span>
            {value === 'isolated' && (
              <Badge variant="default" className="text-xs">Selected</Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            {MARGIN_MODE_INFO.isolated.description}
          </p>
        </button>
      </div>

      {/* Recommendation */}
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Info className="h-3 w-3" />
        <span>
          {value === 'isolated' 
            ? 'Recommended for beginners - limits risk to this position only.'
            : 'Best for experienced traders managing multiple positions.'}
        </span>
      </div>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function DCAFuturesBotConfigDialog({
  open,
  onOpenChange,
  onSubmit,
  initialSymbol = '',
  initialExchange = 'binance_futures',
  availableBalance = 10000,
}: DCAFuturesBotConfigDialogProps) {
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  // Current price state for order preview
  const [currentPrice, setCurrentPrice] = useState<number>(0)
  
  // Section collapse states
  const [marginSettingsOpen, setMarginSettingsOpen] = useState(true)
  const [botSettingsOpen, setBotSettingsOpen] = useState(false)
  const [averagingOrdersOpen, setAveragingOrdersOpen] = useState(true)
  const [positionTpSlOpen, setPositionTpSlOpen] = useState(false)
  const [riskManagementOpen, setRiskManagementOpen] = useState(false)

  const [form, setForm] = useState<FormState>({
    exchange: initialExchange,
    symbol: initialSymbol,
    assetClass: 'crypto',
    strategy: 'long',
    investmentAmount: Math.min(500, availableBalance),
    investmentPercent: Math.min(5, (500 / availableBalance) * 100),
    quickSetup: 'mid_term',
    dcaConfig: { ...DEFAULT_DCA_CONFIG },
    // Futures-specific defaults
    leverage: DEFAULT_LEVERAGE,
    marginMode: DEFAULT_MARGIN_MODE,
  })

  // Fetch current price when symbol changes
  useEffect(() => {
    if (!form.symbol.trim()) {
      setCurrentPrice(0)
      return
    }

    const controller = new AbortController()
    
    const timer = setTimeout(async () => {
      try {
        const quote = await fetchQuote(form.symbol, { signal: controller.signal })
        if (quote?.price) {
          setCurrentPrice(quote.price)
        } else {
          // Use mock prices for futures pairs
          const mockPrices: Record<string, number> = {
            'BTCUSDT': 43250.00,
            'ETHUSDT': 2280.00,
            'BNBUSDT': 310.00,
            'SOLUSDT': 95.00,
            'XRPUSDT': 0.62,
            'DOGEUSDT': 0.085,
          }
          setCurrentPrice(mockPrices[form.symbol.toUpperCase()] || 100.00)
        }
      } catch (err) {
        if (err instanceof Error && err.name !== 'AbortError') {
          setCurrentPrice(100.00)
        }
      }
    }, 300)

    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [form.symbol])

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

  // Calculate estimated PnL (including leverage)
  const estimatedPnL = useMemo(() => {
    const tp = form.dcaConfig.takeProfit?.priceChangePercent || 1
    const amount = form.investmentAmount + (form.dcaConfig.averagingOrders?.totalAmount || 0)
    // With leverage, PnL is multiplied
    return (amount * tp * form.leverage) / 100
  }, [form.investmentAmount, form.dcaConfig, form.leverage])

  // Max position value with leverage
  const maxPositionValue = form.investmentAmount * form.leverage

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
    if (form.leverage < MIN_LEVERAGE || form.leverage > MAX_LEVERAGE) {
      setError(`Leverage must be between ${MIN_LEVERAGE}x and ${MAX_LEVERAGE}x`)
      return
    }

    setIsSubmitting(true)
    setError(null)

    try {
      const totalInvestment = form.investmentAmount + 
        (form.dcaConfig.averagingOrders?.totalAmount || 0)
      
      await onSubmit({
        name: `DCA Futures ${form.symbol} ${form.leverage}x`,
        symbol: form.symbol.trim().toUpperCase(),
        exchange: form.exchange,
        botType: 'futures_dca',
        assetClass: form.assetClass,
        positionMode: form.strategy,
        investmentAmount: totalInvestment,
        dcaConfig: form.dcaConfig,
        // Futures-specific fields
        leverage: form.leverage,
        marginMode: form.marginMode,
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
        investmentAmount: Math.min(500, availableBalance),
        investmentPercent: Math.min(5, (500 / availableBalance) * 100),
        quickSetup: 'mid_term',
        dcaConfig: { ...DEFAULT_DCA_CONFIG },
        leverage: DEFAULT_LEVERAGE,
        marginMode: DEFAULT_MARGIN_MODE,
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
            <TrendingUp className="h-5 w-5 text-primary" />
            Create DCA Futures Bot
            <Badge variant="secondary" className="text-xs">Futures</Badge>
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
                  {FUTURES_EXCHANGES.map(ex => (
                    <SelectItem key={ex.value} value={ex.value}>{ex.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground uppercase">Pair</Label>
              <Input
                placeholder="BTCUSDT"
                value={form.symbol}
                onChange={(e) => updateForm('symbol', e.target.value.toUpperCase())}
              />
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
                  'flex-1 gap-2',
                  form.strategy === 'long' && 'bg-green-600 hover:bg-green-700 text-white'
                )}
                onClick={() => updateForm('strategy', 'long')}
              >
                <TrendingUp className="h-4 w-4" />
                Long
              </Button>
              <Button
                variant={form.strategy === 'short' ? 'default' : 'ghost'}
                className={cn(
                  'flex-1 gap-2',
                  form.strategy === 'short' && 'bg-red-600 hover:bg-red-700 text-white'
                )}
                onClick={() => updateForm('strategy', 'short')}
              >
                <TrendingDown className="h-4 w-4" />
                Short
              </Button>
            </div>
          </div>

          {/* Initial Margin (Investment Amount) */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-xs text-muted-foreground uppercase">
                Initial Margin, USDT
              </Label>
              <span className="text-xs text-muted-foreground">
                ≈ ${availableBalance.toLocaleString()} available
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

          <Separator />

          {/* Margin Settings Section - Futures Specific */}
          <Collapsible open={marginSettingsOpen} onOpenChange={setMarginSettingsOpen}>
            <SectionHeader
              title="Margin Settings"
              isOpen={marginSettingsOpen}
              onToggle={() => setMarginSettingsOpen(!marginSettingsOpen)}
              icon={<Layers className="h-4 w-4 text-primary" />}
            />
            <CollapsibleContent className="space-y-4 pt-4">
              {/* Leverage Selector */}
              <LeverageSelector
                value={form.leverage}
                onChange={(v) => updateForm('leverage', v)}
                investmentAmount={form.investmentAmount}
              />

              {/* Margin Mode Selector */}
              <MarginModeSelector
                value={form.marginMode}
                onChange={(v) => updateForm('marginMode', v)}
              />
            </CollapsibleContent>
          </Collapsible>

          <Separator />

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

          {/* Bot Settings Section - Using shared component */}
          <BotSettingsSection
            isOpen={botSettingsOpen}
            onOpenChange={setBotSettingsOpen}
            dcaConfig={form.dcaConfig}
            onConfigUpdate={updateDcaConfig}
            defaultBaseOrderAmount={form.investmentAmount * 0.2}
            currency="USDT"
            symbol={form.symbol}
            assetClass={form.assetClass}
          />

          <Separator />

          {/* Averaging Orders Section - Using shared component */}
          <AveragingOrdersSection
            isOpen={averagingOrdersOpen}
            onOpenChange={setAveragingOrdersOpen}
            dcaConfig={form.dcaConfig}
            onConfigUpdate={updateDcaConfig}
            currency="USDT"
            currentPrice={currentPrice}
            baseOrderAmount={form.investmentAmount}
            isShort={form.strategy === 'short'}
            assetClass={form.assetClass}
            symbol={form.symbol}
          />

          <Separator />

          {/* Position TP & SL Section - Using shared component with futures-specific warning */}
          <PositionTpSlSection
            isOpen={positionTpSlOpen}
            onOpenChange={setPositionTpSlOpen}
            dcaConfig={form.dcaConfig}
            onConfigUpdate={updateDcaConfig}
            estimatedPnL={estimatedPnL}
            currency="USDT"
            leverage={form.leverage}
            symbol={form.symbol}
            liquidationWarning={
              form.leverage >= 5 && form.dcaConfig.stopLoss?.enabled ? (
                <div className="flex items-start gap-2 p-2 bg-red-500/10 border border-red-500/20 rounded-md">
                  <AlertTriangle className="h-4 w-4 text-red-500 mt-0.5 flex-shrink-0" />
                  <span className="text-xs text-red-600 dark:text-red-400">
                    At {form.leverage}x leverage, a {(100 / form.leverage).toFixed(1)}% move against your position 
                    may result in liquidation. Consider setting stop loss below this level.
                  </span>
                </div>
              ) : undefined
            }
          />

          <Separator />

          {/* Risk Management Section - Using shared component */}
          <RiskManagementSection
            isOpen={riskManagementOpen}
            onOpenChange={setRiskManagementOpen}
            dcaConfig={form.dcaConfig}
            onConfigUpdate={updateDcaConfig}
            totalInvestment={form.investmentAmount}
            currency="USDT"
            currentPrice={currentPrice}
          />

          {/* Position Summary */}
          <div className="space-y-2 p-4 bg-primary/5 rounded-lg border border-primary/20">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Initial Margin</span>
              <span className="font-medium">${form.investmentAmount.toLocaleString()}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Leverage</span>
              <span className="font-medium text-primary">{form.leverage}x</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Max Position Value</span>
              <span className="font-bold text-lg">${maxPositionValue.toLocaleString()}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Margin Mode</span>
              <Badge variant={form.marginMode === 'isolated' ? 'secondary' : 'outline'}>
                {form.marginMode === 'isolated' ? 'Isolated' : 'Cross'}
              </Badge>
            </div>
          </div>

          {/* Available Balance */}
          <div className="flex items-center justify-between text-sm p-3 bg-muted/30 rounded-lg">
            <span className="text-muted-foreground">Available for bot use</span>
            <span className="font-medium">
              ${(availableBalance - totalInvestment).toLocaleString()} USDT
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

export default DCAFuturesBotConfigDialog
