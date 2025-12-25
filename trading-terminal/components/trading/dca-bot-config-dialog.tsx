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
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Combobox, type ComboboxOption } from '@/components/ui/combobox'
import { cn } from '@/lib/utils'
import {
  Info,
  History,
} from 'lucide-react'
import type {
  PositionMode,
  DCAConfig,
  CreateBotRequest,
  QuickSetupPreset,
} from '@/lib/types/bot'
import { DEFAULT_DCA_CONFIG, QUICK_SETUP_PRESETS } from '@/lib/types/bot'
import type { AssetClass } from '@/lib/types/asset'
import {
  getSymbolsForExchange,
  symbolsToComboboxOptions,
  getSupportedAssetClasses,
  exchangeSupportsAssetClass,
} from '@/lib/data/exchange-symbols'
import { fetchQuote } from '@/lib/api'

// Import shared components
import {
  AveragingOrdersSection,
  PositionTpSlSection,
  RiskManagementSection,
  BotSettingsSection,
} from './shared'

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

const ALL_ASSET_CLASSES: { value: AssetClass; label: string }[] = [
  { value: 'crypto', label: 'Crypto' },
  { value: 'stock', label: 'Stocks' },
  { value: 'forex', label: 'Forex' },
  { value: 'etf', label: 'ETF' },
]

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
  
  // Current price state for order preview
  const [currentPrice, setCurrentPrice] = useState<number>(0)
  const [isPriceFetching, setIsPriceFetching] = useState(false)
  
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

  // Fetch current price when symbol changes
  useEffect(() => {
    if (!form.symbol.trim()) {
      setCurrentPrice(0)
      return
    }

    const controller = new AbortController()
    setIsPriceFetching(true)
    
    // Debounce the fetch
    const timer = setTimeout(async () => {
      try {
        const quote = await fetchQuote(form.symbol, { signal: controller.signal })
        if (quote?.price) {
          setCurrentPrice(quote.price)
        } else {
          // Use mock prices for demo if API unavailable
          const mockPrices: Record<string, number> = {
            'BTC/USD': 43250.00,
            'ETH/USD': 2280.00,
            'AAPL': 178.50,
            'MSFT': 374.20,
            'GOOGL': 140.80,
            'TSLA': 248.50,
            'NVDA': 495.00,
            'SPY': 475.00,
          }
          setCurrentPrice(mockPrices[form.symbol.toUpperCase()] || 100.00)
        }
      } catch (err) {
        if (err instanceof Error && err.name !== 'AbortError') {
          console.warn('Failed to fetch price:', err)
          // Set a default price for visualization
          setCurrentPrice(100.00)
        }
      } finally {
        setIsPriceFetching(false)
      }
    }, 300)

    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [form.symbol])

  // Available asset classes for selected exchange
  const availableAssetClasses = useMemo(() => {
    const supported = getSupportedAssetClasses(form.exchange)
    return ALL_ASSET_CLASSES.filter(ac => supported.includes(ac.value))
  }, [form.exchange])

  // Symbol options based on exchange and asset class
  const symbolOptions = useMemo((): ComboboxOption[] => {
    const symbols = getSymbolsForExchange(form.exchange, form.assetClass)
    return symbolsToComboboxOptions(symbols, true)
  }, [form.exchange, form.assetClass])

  // Reset asset class when exchange changes if current class not supported
  useEffect(() => {
    if (!exchangeSupportsAssetClass(form.exchange, form.assetClass)) {
      const supported = getSupportedAssetClasses(form.exchange)
      if (supported.length > 0) {
        setForm(prev => ({
          ...prev,
          assetClass: supported[0],
          symbol: '', // Reset symbol when asset class changes
        }))
      }
    }
  }, [form.exchange, form.assetClass])

  // Reset symbol when asset class changes
  const handleAssetClassChange = useCallback((newAssetClass: AssetClass) => {
    setForm(prev => ({
      ...prev,
      assetClass: newAssetClass,
      symbol: '', // Reset symbol when asset class changes
    }))
  }, [])

  // Sync investment amount when base order or averaging orders change
  useEffect(() => {
    const baseOrder = form.dcaConfig.startSettings?.baseOrderAmount || 0
    const avgOrders = form.dcaConfig.averagingOrders?.totalAmount || 0
    const newTotal = baseOrder + avgOrders
    
    // Only update if there's a meaningful difference (avoid floating point issues)
    setForm(prev => {
      if (Math.abs(newTotal - prev.investmentAmount) > 0.001) {
        return {
          ...prev,
          investmentAmount: Math.round(newTotal * 100) / 100,
          investmentPercent: Math.round((newTotal / availableBalance) * 10000) / 100,
        }
      }
      return prev
    })
  }, [form.dcaConfig.startSettings?.baseOrderAmount, form.dcaConfig.averagingOrders?.totalAmount, availableBalance])

  /**
   * Sanitize numeric input to prevent invalid values like "0988".
   * Parses the input and returns a clean number.
   */
  const sanitizeNumericInput = useCallback((value: string): number => {
    // Remove leading zeros and parse as float
    const cleaned = value.replace(/^0+(?=\d)/, '')
    const num = parseFloat(cleaned)
    return isNaN(num) ? 0 : Math.round(num * 100) / 100
  }, [])

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
    const tp = form.dcaConfig.takeProfit?.priceChangePercent || 1
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
          {/* Exchange, Asset Type & Pair Selection */}
          <div className="space-y-4">
            {/* Exchange Selection */}
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

            {/* Asset Type Selection */}
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground uppercase">Asset Type</Label>
              <Select 
                value={form.assetClass} 
                onValueChange={(v) => handleAssetClassChange(v as AssetClass)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {availableAssetClasses.map(ac => (
                    <SelectItem key={ac.value} value={ac.value}>{ac.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {availableAssetClasses.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  No asset classes available for this exchange
                </p>
              )}
            </div>

            {/* Pair/Symbol Selection - Searchable Combobox */}
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground uppercase">
                {form.assetClass === 'stock' || form.assetClass === 'etf' ? 'Symbol' : 'Pair'}
              </Label>
              <Combobox
                options={symbolOptions}
                value={form.symbol}
                onValueChange={(v) => updateForm('symbol', v)}
                placeholder={
                  form.assetClass === 'stock' || form.assetClass === 'etf'
                    ? 'Search symbol (e.g., AAPL, MSFT)...'
                    : 'Search pair (e.g., BTC/USD, ETH/USDT)...'
                }
                emptyMessage={
                  symbolOptions.length === 0
                    ? `No ${form.assetClass} symbols available for ${form.exchange}`
                    : 'No matching symbols found'
                }
                allowCustomValue={true}
              />
              {symbolOptions.length === 0 && (
                <p className="text-xs text-yellow-600 dark:text-yellow-400">
                  Enter a custom symbol or select a different asset type/exchange
                </p>
              )}
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
                Investment, {form.strategy === 'short' ? (form.symbol.split('/')[0] || 'USD') : 'USD'}
              </Label>
              <span className="text-xs text-muted-foreground">
                ≈ ${availableBalance.toLocaleString()} USD
              </span>
            </div>
            
            <div className="flex items-center gap-3">
              <Input
                type="number"
                min={0}
                step="0.01"
                value={form.investmentAmount}
                onChange={(e) => {
                  const val = sanitizeNumericInput(e.target.value)
                  updateForm('investmentAmount', val)
                  updateForm('investmentPercent', (val / availableBalance) * 100)
                }}
                onBlur={(e) => {
                  // Ensure clean value on blur
                  const val = sanitizeNumericInput(e.target.value)
                  e.target.value = val.toString()
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

          {/* Bot Settings Section - Using shared component */}
          <BotSettingsSection
            isOpen={botSettingsOpen}
            onOpenChange={setBotSettingsOpen}
            dcaConfig={form.dcaConfig}
            onConfigUpdate={updateDcaConfig}
            defaultBaseOrderAmount={form.investmentAmount * 0.2}
            currency={form.strategy === 'short' ? (form.symbol.split('/')[0] || 'USD') : 'USD'}
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
            currency={form.symbol.split('/')[0] || 'USD'}
            currentPrice={currentPrice}
            baseOrderAmount={form.dcaConfig.startSettings?.baseOrderAmount || form.investmentAmount * 0.2}
            isShort={form.strategy === 'short'}
            assetClass={form.assetClass}
          />

          <Separator />

          {/* Position TP & SL Section - Using shared component */}
          <PositionTpSlSection
            isOpen={positionTpSlOpen}
            onOpenChange={setPositionTpSlOpen}
            dcaConfig={form.dcaConfig}
            onConfigUpdate={updateDcaConfig}
            estimatedPnL={estimatedPnL}
            currency={form.symbol.split('/')[0] || 'USD'}
            symbol={form.symbol}
          />

          <Separator />

          {/* Risk Management Section - Using shared component */}
          <RiskManagementSection
            isOpen={riskManagementOpen}
            onOpenChange={setRiskManagementOpen}
            dcaConfig={form.dcaConfig}
            onConfigUpdate={updateDcaConfig}
            totalInvestment={totalInvestment}
            currency="USD"
            currentPrice={currentPrice}
          />

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
