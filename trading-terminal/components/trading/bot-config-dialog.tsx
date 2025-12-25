/**
 * Bot Configuration Dialog
 * 
 * Two-step wizard dialog for creating new trading bots:
 * Step 1: Select bot type (GRID, DCA, BTD, LOOP, etc.)
 * Step 2: Configure the selected bot strategy (opens specialized dialog for DCA)
 * 
 * UI inspired by Bitsgap "Start new bot" dialog.
 * 
 * @module components/trading/bot-config-dialog
 */

'use client'

import React, { useState, useCallback } from 'react'
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
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  TrendingUp,
  TrendingDown,
  Settings,
  DollarSign,
  AlertTriangle,
  Grid3X3,
  RefreshCw,
  Repeat,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Layers,
} from 'lucide-react'
import type {
  BotType,
  PositionMode,
  MarginMode,
  DCAConfig,
  CreateBotRequest,
} from '@/lib/types/bot'
import { DEFAULT_DCA_CONFIG } from '@/lib/types/bot'
import { AssetClass } from '@/lib/types/asset'
import { DCABotConfigDialog } from './dca-bot-config-dialog'
import { DCAFuturesBotConfigDialog } from './dca-futures-bot-config-dialog'

// ============================================================================
// Types
// ============================================================================

interface BotConfigDialogProps {
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
  name: string
  symbol: string
  exchange: string
  botType: BotType
  assetClass: AssetClass
  positionMode: PositionMode
  marginMode: MarginMode
  investmentAmount: string
  leverage: number
  dcaConfig: DCAConfig
}

type MarketType = 'spot' | 'futures'

interface BotTypeOption {
  value: BotType
  label: string
  description: string
  icon: React.ReactNode
  badges: { label: string; variant: 'default' | 'success' | 'warning' | 'info' }[]
  spotOnly?: boolean
  futuresOnly?: boolean
}

// ============================================================================
// Constants
// ============================================================================

const EXCHANGES = [
  { value: 'alpaca', label: 'Alpaca (Stocks)' },
  { value: 'coinbase', label: 'Coinbase (Crypto)' },
  { value: 'binance', label: 'Binance (Crypto)' },
  { value: 'kraken', label: 'Kraken (Crypto)' },
]

const BOT_TYPE_OPTIONS: BotTypeOption[] = [
  // ---- SPOT BOTS ----
  {
    value: 'grid',
    label: 'GRID Bot',
    description: 'Profit from every price movement. Generate gains from small price fluctuations in sideways markets.',
    icon: <Grid3X3 className="h-5 w-5" />,
    badges: [{ label: 'Sideways', variant: 'info' }, { label: 'Spot', variant: 'success' }],
    spotOnly: true,
  },
  {
    value: 'dca',
    label: 'DCA Bot',
    description: 'Low-risk earnings in volatile markets. Buy at multiple price levels to reduce average cost.',
    icon: <Layers className="h-5 w-5" />,
    badges: [{ label: 'Long', variant: 'success' }, { label: 'Spot', variant: 'success' }],
    spotOnly: true,
  },
  {
    value: 'btd',
    label: 'BTD Bot',
    description: 'Rising yields from falling prices. Automatically buy the dip and profit when markets recover.',
    icon: <TrendingDown className="h-5 w-5" />,
    badges: [{ label: 'Dip Buyer', variant: 'warning' }, { label: 'Spot', variant: 'success' }],
    spotOnly: true,
  },
  {
    value: 'spot_loop',
    label: 'LOOP Bot',
    description: 'Profit both ways and amplify growth. Earn in both currencies and auto-reinvest for compounding gains.',
    icon: <Repeat className="h-5 w-5" />,
    badges: [{ label: 'Sideways', variant: 'info' }, { label: 'Reinvest', variant: 'success' }, { label: 'Spot', variant: 'success' }],
    spotOnly: true,
  },
  // ---- FUTURES BOTS ----
  {
    value: 'futures_dca',
    label: 'DCA Futures Bot',
    description: 'Structured gains from futures volatility. Use DCA strategy with up to 10x leverage.',
    icon: <Layers className="h-5 w-5" />,
    badges: [{ label: 'Futures', variant: 'warning' }, { label: 'Leverage', variant: 'info' }],
    futuresOnly: true,
  },
  {
    value: 'futures_combo',
    label: 'COMBO Bot',
    description: 'High risks & returns in futures trading. Combines GRID + DCA strategies with up to 10x leverage.',
    icon: <RefreshCw className="h-5 w-5" />,
    badges: [{ label: 'Futures', variant: 'warning' }, { label: 'High Risk', variant: 'warning' }, { label: 'Leverage', variant: 'info' }],
    futuresOnly: true,
  },
]

// ============================================================================
// Sub-components
// ============================================================================

/**
 * Bot Type Selection Card
 * 
 * Renders a selectable card showing bot type with icon, badges, and description.
 */
function BotTypeCard({
  option,
  isSelected,
  onClick,
}: {
  option: BotTypeOption
  isSelected: boolean
  onClick: () => void
}) {
  const badgeColors = {
    default: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
    success: 'bg-green-500/20 text-green-400 border-green-500/30',
    warning: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    info: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  }

  return (
    <div
      onClick={onClick}
      className={`
        flex items-start gap-4 p-4 rounded-lg cursor-pointer transition-all
        border hover:bg-muted/50
        ${isSelected ? 'ring-2 ring-primary bg-primary/5 border-primary' : 'border-border'}
      `}
    >
      <div className={`
        h-10 w-10 rounded-full flex items-center justify-center flex-shrink-0
        ${isSelected ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}
      `}>
        {option.icon}
      </div>
      
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold">{option.label}</span>
          {option.badges.map((badge, idx) => (
            <Badge
              key={idx}
              variant="outline"
              className={`text-xs ${badgeColors[badge.variant]}`}
            >
              {badge.label}
            </Badge>
          ))}
        </div>
        <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
          {option.description}
        </p>
      </div>

      <ChevronRight className={`h-5 w-5 flex-shrink-0 transition-colors ${
        isSelected ? 'text-primary' : 'text-muted-foreground'
      }`} />
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function BotConfigDialog({
  open,
  onOpenChange,
  onSubmit,
  initialSymbol = '',
  initialExchange = 'alpaca',
  availableBalance = 10000,
}: BotConfigDialogProps) {
  // Wizard step: 1 = select bot type, 2 = configure bot (or open specialized dialog)
  const [step, setStep] = useState<1 | 2>(1)
  const [marketType, setMarketType] = useState<MarketType>('spot')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showDcaDialog, setShowDcaDialog] = useState(false)
  const [showDcaFuturesDialog, setShowDcaFuturesDialog] = useState(false)
  
  const [form, setForm] = useState<FormState>({
    name: '',
    symbol: initialSymbol,
    exchange: initialExchange,
    botType: 'dca',
    assetClass: 'stock',
    positionMode: 'long',
    marginMode: 'isolated',
    investmentAmount: '1000',
    leverage: 1,
    dcaConfig: { ...DEFAULT_DCA_CONFIG },
  })

  // Filter bot types based on market type
  const availableBotTypes = BOT_TYPE_OPTIONS.filter(opt => {
    if (marketType === 'spot' && opt.futuresOnly) return false
    if (marketType === 'futures' && opt.spotOnly) return false
    return true
  })

  const updateForm = useCallback(<K extends keyof FormState>(
    key: K,
    value: FormState[K]
  ) => {
    setForm(prev => ({ ...prev, [key]: value }))
    setError(null)
  }, [])

  // Note: updateDcaConfig removed - DCA/Futures DCA bots route to
  // specialized dialogs (DCABotConfigDialog, DCAFuturesBotConfigDialog)
  // which have their own proper DCA configuration handling.

  const handleSelectBotType = (botType: BotType) => {
    updateForm('botType', botType)
    // Auto-set leverage for futures bots
    if (botType.includes('futures') || marketType === 'futures') {
      updateForm('leverage', 3)
    }
  }

  const handleProceedToConfig = () => {
    // For DCA bots, open the specialized DCA configuration dialog
    if (form.botType === 'dca') {
      onOpenChange(false) // Close the type selection dialog
      setShowDcaDialog(true) // Open DCA config dialog
    } else if (form.botType === 'futures_dca') {
      onOpenChange(false) // Close the type selection dialog
      setShowDcaFuturesDialog(true) // Open DCA Futures config dialog
    } else {
      setStep(2) // For other bot types, proceed to generic config
    }
  }

  const handleDcaDialogClose = (open: boolean) => {
    setShowDcaDialog(open)
    if (!open) {
      // Reset the main dialog state when DCA dialog closes
      setStep(1)
    }
  }

  const handleDcaFuturesDialogClose = (open: boolean) => {
    setShowDcaFuturesDialog(open)
    if (!open) {
      // Reset the main dialog state when DCA Futures dialog closes
      setStep(1)
    }
  }

  const handleDcaSubmit = async (request: CreateBotRequest) => {
    await onSubmit(request)
    setShowDcaDialog(false)
    setStep(1)
  }

  const handleDcaFuturesSubmit = async (request: CreateBotRequest) => {
    await onSubmit(request)
    setShowDcaFuturesDialog(false)
    setStep(1)
  }

  const handleBack = () => {
    setStep(1)
    setError(null)
  }

  const handleClose = () => {
    onOpenChange(false)
    // Reset state after animation
    setTimeout(() => {
      setStep(1)
      setError(null)
      setShowDcaDialog(false)
      setShowDcaFuturesDialog(false)
      setForm({
        name: '',
        symbol: '',
        exchange: initialExchange,
        botType: 'dca',
        assetClass: 'stock',
        positionMode: 'long',
        marginMode: 'isolated',
        investmentAmount: '1000',
        leverage: 1,
        dcaConfig: { ...DEFAULT_DCA_CONFIG },
      })
    }, 200)
  }

  const handleSubmit = async () => {
    // Validation
    if (!form.name.trim()) {
      setError('Bot name is required')
      return
    }
    if (!form.symbol.trim()) {
      setError('Symbol is required')
      return
    }
    const amount = parseFloat(form.investmentAmount)
    if (isNaN(amount) || amount <= 0) {
      setError('Investment amount must be a positive number')
      return
    }

    setIsSubmitting(true)
    setError(null)

    try {
      await onSubmit({
        name: form.name.trim(),
        symbol: form.symbol.trim().toUpperCase(),
        exchange: form.exchange,
        botType: form.botType,
        assetClass: form.assetClass,
        positionMode: form.positionMode,
        marginMode: form.marginMode,
        investmentAmount: amount,
        leverage: form.leverage,
        dcaConfig: form.dcaConfig,
      })
      handleClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create bot')
    } finally {
      setIsSubmitting(false)
    }
  }

  const isFutures = form.botType.includes('futures') || marketType === 'futures'
  const selectedBotOption = BOT_TYPE_OPTIONS.find(o => o.value === form.botType)

  return (
    <>
      {/* DCA Bot Configuration Dialog */}
      <DCABotConfigDialog
        open={showDcaDialog}
        onOpenChange={handleDcaDialogClose}
        onSubmit={handleDcaSubmit}
        initialSymbol={form.symbol}
        initialExchange={form.exchange}
        availableBalance={availableBalance}
      />

      {/* DCA Futures Bot Configuration Dialog */}
      <DCAFuturesBotConfigDialog
        open={showDcaFuturesDialog}
        onOpenChange={handleDcaFuturesDialogClose}
        onSubmit={handleDcaFuturesSubmit}
        initialSymbol={form.symbol}
        initialExchange="binance_futures"
        availableBalance={availableBalance}
      />

      {/* Main Bot Type Selection Dialog */}
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent className={`${step === 1 ? 'max-w-lg' : 'max-w-2xl'} max-h-[90vh] overflow-hidden flex flex-col`}>
          {/* Header */}
          <DialogHeader className="flex-shrink-0">
            <DialogTitle className="text-xl">
              {step === 1 ? 'Start new bot' : `Configure ${selectedBotOption?.label || 'Bot'}`}
            </DialogTitle>
          </DialogHeader>

          {/* Step 1: Select Bot Type */}
          {step === 1 && (
            <div className="flex-1 overflow-y-auto py-4">
              {/* Market Type Toggle */}
              <div className="flex rounded-lg border p-1 mb-6">
              <Button
                variant={marketType === 'spot' ? 'default' : 'ghost'}
                className="flex-1"
                onClick={() => setMarketType('spot')}
              >
                Spot
              </Button>
              <Button
                variant={marketType === 'futures' ? 'default' : 'ghost'}
                className="flex-1"
                onClick={() => setMarketType('futures')}
              >
                Futures
              </Button>
            </div>

            {/* Bot Type Options */}
            <div className="space-y-3">
              {availableBotTypes.map((option) => (
                <BotTypeCard
                  key={option.value}
                  option={option}
                  isSelected={form.botType === option.value}
                  onClick={() => handleSelectBotType(option.value)}
                />
              ))}
            </div>

            {/* Learn More Link */}
            <div className="mt-6 text-center">
              <a
                href="/strategies"
                className="text-sm text-primary hover:underline inline-flex items-center gap-1"
              >
                Learn more about different bot strategies
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          </div>
        )}

        {/* Step 2: Configure Bot */}
        {step === 2 && (
          <div className="flex-1 overflow-y-auto py-4 space-y-6">
            {/* Basic Info */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="name">Bot Name</Label>
                <Input
                  id="name"
                  placeholder="My DCA Bot"
                  value={form.name}
                  onChange={(e) => updateForm('name', e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="symbol">Symbol</Label>
                <Input
                  id="symbol"
                  placeholder="AAPL or BTC/USD"
                  value={form.symbol}
                  onChange={(e) => updateForm('symbol', e.target.value.toUpperCase())}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Exchange</Label>
                <Select value={form.exchange} onValueChange={(v) => updateForm('exchange', v)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {EXCHANGES.map((ex) => (
                      <SelectItem key={ex.value} value={ex.value}>
                        {ex.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Asset Class</Label>
                <Select
                  value={form.assetClass}
                  onValueChange={(v) => updateForm('assetClass', v as AssetClass)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="stock">Stocks</SelectItem>
                    <SelectItem value="crypto">Crypto</SelectItem>
                    <SelectItem value="forex">Forex</SelectItem>
                    <SelectItem value="etf">ETF</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Position Direction */}
            <div className="space-y-2">
              <Label>Position Direction</Label>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant={form.positionMode === 'long' ? 'default' : 'outline'}
                  onClick={() => updateForm('positionMode', 'long')}
                  className={`flex-1 ${form.positionMode === 'long' ? 'bg-green-600 hover:bg-green-700' : ''}`}
                >
                  <TrendingUp className="h-4 w-4 mr-2" />
                  Long
                </Button>
                <Button
                  type="button"
                  variant={form.positionMode === 'short' ? 'default' : 'outline'}
                  onClick={() => updateForm('positionMode', 'short')}
                  className={`flex-1 ${form.positionMode === 'short' ? 'bg-red-600 hover:bg-red-700' : ''}`}
                >
                  <TrendingDown className="h-4 w-4 mr-2" />
                  Short
                </Button>
                <Button
                  type="button"
                  variant={form.positionMode === 'both' ? 'default' : 'outline'}
                  onClick={() => updateForm('positionMode', 'both')}
                  className="flex-1"
                >
                  <Settings className="h-4 w-4 mr-2" />
                  Both
                </Button>
              </div>
            </div>

            {/* Investment */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center gap-2">
                  <DollarSign className="h-4 w-4" />
                  Investment
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="amount">Investment Amount ($)</Label>
                    <Input
                      id="amount"
                      type="number"
                      min="0"
                      step="100"
                      value={form.investmentAmount}
                      onChange={(e) => updateForm('investmentAmount', e.target.value)}
                    />
                  </div>
                  {isFutures && (
                    <div className="space-y-2">
                      <Label>Leverage: {form.leverage}x</Label>
                      <Slider
                        value={[form.leverage]}
                        onValueChange={([v]) => updateForm('leverage', v)}
                        min={1}
                        max={50}
                        step={1}
                        className="mt-2"
                      />
                      {form.leverage > 10 && (
                        <div className="flex items-center gap-1 text-xs text-yellow-500">
                          <AlertTriangle className="h-3 w-3" />
                          High leverage increases risk
                        </div>
                      )}
                    </div>
                  )}
                </div>
                
                {isFutures && (
                  <div className="space-y-2">
                    <Label>Margin Mode</Label>
                    <div className="flex gap-2">
                      <Button
                        type="button"
                        variant={form.marginMode === 'isolated' ? 'default' : 'outline'}
                        onClick={() => updateForm('marginMode', 'isolated')}
                        size="sm"
                      >
                        Isolated
                      </Button>
                      <Button
                        type="button"
                        variant={form.marginMode === 'cross' ? 'default' : 'outline'}
                        onClick={() => updateForm('marginMode', 'cross')}
                        size="sm"
                      >
                        Cross
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Note: DCA Settings removed from Step 2 
                DCA and Futures DCA bots route to specialized dialogs:
                - DCABotConfigDialog for DCA bots
                - DCAFuturesBotConfigDialog for Futures DCA bots
                
                This Step 2 is only used for GRID, COMBO, and LOOP bots
                which will have their own specialized configuration dialogs
                implemented in the future.
            */}

            {/* Error Display */}
            {error && (
              <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-500 text-sm">
                {error}
              </div>
            )}
          </div>
        )}

        {/* Footer */}
        <DialogFooter className="flex-shrink-0 border-t pt-4">
          {step === 1 ? (
            <>
              <Button variant="outline" onClick={handleClose}>
                Cancel
              </Button>
              <Button onClick={handleProceedToConfig}>
                Continue
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={handleBack}>
                <ChevronLeft className="h-4 w-4 mr-1" />
                Back
              </Button>
              <Button onClick={handleSubmit} disabled={isSubmitting}>
                {isSubmitting ? 'Creating...' : 'Create Bot'}
              </Button>
            </>
          )}
        </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export default BotConfigDialog
