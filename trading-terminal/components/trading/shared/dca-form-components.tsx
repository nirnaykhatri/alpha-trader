/**
 * Shared DCA Bot Form Components
 * 
 * Reusable form components used by both DCA spot and DCA futures dialogs.
 * Extracted to reduce code duplication (~200+ lines saved).
 * 
 * @module components/trading/shared/dca-form-components
 */

'use client'

import React from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { CollapsibleTrigger } from '@/components/ui/collapsible'
import { ChevronDown, ChevronRight, Minus, Plus, AlertTriangle, Info, Loader2 } from 'lucide-react'
import { useDebouncedNumericInput, useDCAPreview } from '@/lib/hooks'
import type { AssetClass, Strategy } from '@/lib/types/dca-preview'

// ============================================================================
// SectionHeader - Collapsible section toggle
// ============================================================================

export interface SectionHeaderProps {
  /** Section title text */
  title: string
  /** Whether the section is expanded */
  isOpen: boolean
  /** Toggle callback */
  onToggle: () => void
  /** Optional icon to display before title */
  icon?: React.ReactNode
}

/**
 * Collapsible Section Header with chevron indicator.
 * 
 * @example
 * ```tsx
 * <Collapsible>
 *   <SectionHeader
 *     title="Bot Settings"
 *     isOpen={isOpen}
 *     onToggle={() => setIsOpen(!isOpen)}
 *     icon={<Settings className="h-4 w-4" />}
 *   />
 *   <CollapsibleContent>...</CollapsibleContent>
 * </Collapsible>
 * ```
 */
export function SectionHeader({
  title,
  isOpen,
  onToggle,
  icon,
}: SectionHeaderProps) {
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

// ============================================================================
// NumberStepper - Numeric input with +/- buttons
// ============================================================================

export interface NumberStepperProps {
  /** Current value */
  value: number
  /** Change handler */
  onChange: (value: number) => void
  /** Minimum allowed value */
  min?: number
  /** Maximum allowed value */
  max?: number
  /** Step increment/decrement amount */
  step?: number
  /** Label text above the control */
  label?: string
  /** Suffix text after the value (e.g., "x", "%") */
  suffix?: string
}

/**
 * Number Input with increment/decrement buttons.
 * 
 * @example
 * ```tsx
 * <NumberStepper
 *   label="Orders Quantity"
 *   value={4}
 *   onChange={setOrderCount}
 *   min={1}
 *   max={100}
 *   suffix="orders"
 * />
 * ```
 */
export function NumberStepper({
  value,
  onChange,
  min = 0,
  max = 100,
  step = 1,
  label,
  suffix,
}: NumberStepperProps) {
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
          type="button"
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
          type="button"
        >
          <Plus className="h-3 w-3" />
        </Button>
      </div>
    </div>
  )
}

// ============================================================================
// MultiplierSlider - Toggle-enabled slider with multiplier display
// ============================================================================

export interface MultiplierSliderProps {
  /** Label text */
  label: string
  /** Current multiplier value */
  value: number
  /** Whether the multiplier is enabled */
  enabled: boolean
  /** Value change handler */
  onValueChange: (value: number) => void
  /** Enabled state change handler */
  onEnabledChange: (enabled: boolean) => void
  /** Minimum multiplier value */
  min?: number
  /** Maximum multiplier value */
  max?: number
  /** Step increment */
  step?: number
}

/**
 * Multiplier slider with toggle switch.
 * Shows "Off" state when disabled, slider when enabled.
 * 
 * @example
 * ```tsx
 * <MultiplierSlider
 *   label="Amount Multiplier"
 *   value={1.3}
 *   enabled={true}
 *   onValueChange={setValue}
 *   onEnabledChange={setEnabled}
 *   min={1}
 *   max={3}
 *   step={0.1}
 * />
 * ```
 */
export function MultiplierSlider({
  label,
  value,
  enabled,
  onValueChange,
  onEnabledChange,
  min = 1,
  max = 3,
  step = 0.1,
}: MultiplierSliderProps) {
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
// PercentInput - Styled percentage input field with debouncing
// ============================================================================

export interface PercentInputProps {
  /** Current value (without %) */
  value: number
  /** Change handler */
  onChange: (value: number) => void
  /** Label text */
  label: string
  /** Step increment for input */
  step?: number
  /** Additional info icon */
  showInfo?: boolean
  /** Debounce delay in ms (default: 300ms, set to 0 to disable) */
  debounceMs?: number
}

/**
 * Percentage input field with label and debouncing.
 * 
 * Uses 300ms debounce by default to prevent excessive re-renders
 * when users type rapidly. Set debounceMs to 0 to disable.
 * 
 * @example
 * ```tsx
 * <PercentInput
 *   label="Averaging orders step"
 *   value={1.99}
 *   onChange={setStepPercent}
 *   step={0.01}
 * />
 * ```
 */
export function PercentInput({
  value,
  onChange,
  label,
  step = 0.01,
  debounceMs = 300,
}: PercentInputProps) {
  const {
    displayValue,
    handleChange,
    handleBlur,
    isInvalid,
    hasError,
  } = useDebouncedNumericInput(value, onChange, debounceMs)
  
  return (
    <div className="space-y-2">
      <Label className="text-xs text-muted-foreground">{label}, %</Label>
      <Input
        type="number"
        step={step}
        value={displayValue}
        onChange={(e) => handleChange(e.target.value)}
        onBlur={handleBlur}
        className={isInvalid ? 'border-destructive' : hasError ? 'border-yellow-500' : ''}
      />
      {hasError && (
        <p className="text-xs text-yellow-600">Value reset to 0</p>
      )}
    </div>
  )
}

// ============================================================================
// AmountInput - Currency amount input field with debouncing
// ============================================================================

export interface AmountInputProps {
  /** Current value */
  value: number
  /** Change handler */
  onChange: (value: number) => void
  /** Label text */
  label: string
  /** Currency suffix (e.g., "USD", "USDT") */
  currency?: string
  /** Debounce delay in ms (default: 300ms, set to 0 to disable) */
  debounceMs?: number
}

/**
 * Amount input field with currency label and debouncing.
 * 
 * Uses 300ms debounce by default to prevent excessive re-renders
 * when users type rapidly. Set debounceMs to 0 to disable.
 * 
 * @example
 * ```tsx
 * <AmountInput
 *   label="Averaging orders amount"
 *   value={800}
 *   onChange={setAmount}
 *   currency="USDT"
 * />
 * ```
 */
export function AmountInput({
  value,
  onChange,
  label,
  currency = 'USD',
  debounceMs = 300,
}: AmountInputProps) {
  const {
    displayValue,
    handleChange,
    handleBlur,
    isInvalid,
    hasError,
  } = useDebouncedNumericInput(value, onChange, debounceMs)
  
  return (
    <div className="space-y-2">
      <Label className="text-xs text-muted-foreground">
        {label}, {currency}
      </Label>
      <Input
        type="number"
        value={displayValue}
        onChange={(e) => handleChange(e.target.value)}
        onBlur={handleBlur}
        className={isInvalid ? 'border-destructive' : hasError ? 'border-yellow-500' : ''}
      />
      {hasError && (
        <p className="text-xs text-yellow-600">Value reset to 0</p>
      )}
    </div>
  )
}

// ============================================================================
// OrderTypeToggle - Limit/Market order type selector
// ============================================================================

export interface OrderTypeToggleProps {
  /** Current order type */
  value: 'limit' | 'market'
  /** Change handler */
  onChange: (value: 'limit' | 'market') => void
}

/**
 * Toggle button group for order type selection.
 * 
 * @example
 * ```tsx
 * <OrderTypeToggle
 *   value="limit"
 *   onChange={setOrderType}
 * />
 * ```
 */
export function OrderTypeToggle({
  value,
  onChange,
}: OrderTypeToggleProps) {
  return (
    <div className="flex rounded-lg border p-1">
      <Button
        variant={value === 'limit' ? 'default' : 'ghost'}
        size="sm"
        className="flex-1"
        onClick={() => onChange('limit')}
        type="button"
      >
        Limit
      </Button>
      <Button
        variant={value === 'market' ? 'default' : 'ghost'}
        size="sm"
        className="flex-1"
        onClick={() => onChange('market')}
        type="button"
      >
        Market
      </Button>
    </div>
  )
}

// ============================================================================
// ToggleRow - Simple label + switch row
// ============================================================================

export interface ToggleRowProps {
  /** Label text */
  label: string
  /** Current checked state */
  checked: boolean
  /** Change handler */
  onCheckedChange: (checked: boolean) => void
  /** Optional icon before label */
  icon?: React.ReactNode
}

/**
 * Simple row with label and toggle switch.
 * 
 * @example
 * ```tsx
 * <ToggleRow
 *   label="Pump / Dump Protection"
 *   checked={true}
 *   onCheckedChange={setEnabled}
 * />
 * ```
 */
export function ToggleRow({
  label,
  checked,
  onCheckedChange,
  icon,
}: ToggleRowProps) {
  return (
    <div className="flex items-center justify-between">
      <Label className="text-sm flex items-center gap-2">
        {icon}
        {label}
      </Label>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  )
}

// ============================================================================
// DCA Order Preview Table - Visual breakdown of all orders
// ============================================================================

export interface DCAOrderPreviewProps {
  /** Trading symbol (e.g., 'AAPL', 'BTC/USD') */
  symbol: string
  /** Base order amount */
  baseOrderAmount: number
  /** Total amount for averaging orders */
  averagingOrdersAmount: number
  /** Number of averaging orders */
  ordersCount: number
  /** Step percentage between orders */
  stepPercent: number
  /** Amount multiplier (1.0 = no multiplier) */
  amountMultiplier: number
  /** Whether amount multiplier is enabled */
  amountMultiplierEnabled: boolean
  /** Step multiplier (1.0 = no multiplier) */
  stepMultiplier: number
  /** Whether step multiplier is enabled */
  stepMultiplierEnabled: boolean
  /** Current price of the asset */
  currentPrice: number
  /** Currency symbol for display */
  currency?: string
  /** Whether this is a short position (prices go up instead of down) */
  isShort?: boolean
  /** Callback to fix invalid configuration */
  onFixConfig?: (newOrdersCount: number, newStepPercent: number) => void
  /** Asset class - determines if fractional units are allowed */
  assetClass?: AssetClass
}

/**
 * DCA Order Preview Table Component.
 * 
 * Fetches order preview data from the backend API using the useDCAPreview hook.
 * The backend is the single source of truth for all DCA calculations.
 * 
 * Features:
 * - Live updates with debounced API calls (300ms)
 * - Stale-while-revalidate pattern for smooth UX
 * - Request cancellation for rapid changes
 * - Validation errors and suggested fixes from API
 * 
 * @example
 * ```tsx
 * <DCAOrderPreview
 *   symbol="AAPL"
 *   baseOrderAmount={100}
 *   averagingOrdersAmount={500}
 *   ordersCount={5}
 *   stepPercent={1.5}
 *   amountMultiplier={1.3}
 *   amountMultiplierEnabled={true}
 *   stepMultiplier={1.2}
 *   stepMultiplierEnabled={true}
 *   currentPrice={150.00}
 *   currency="USD"
 *   onFixConfig={(count, step) => updateConfig(count, step)}
 * />
 * ```
 */
export function DCAOrderPreview({
  symbol,
  baseOrderAmount,
  averagingOrdersAmount,
  ordersCount,
  stepPercent,
  amountMultiplier,
  amountMultiplierEnabled,
  stepMultiplier,
  stepMultiplierEnabled,
  currentPrice,
  currency = 'USD',
  isShort = false,
  onFixConfig,
  assetClass = 'crypto',
}: DCAOrderPreviewProps) {
  // Fetch preview from backend API using the hook
  // Gate API calls - only fetch when we have a valid price
  const strategy: Strategy = isShort ? 'short' : 'long'
  const { data, isLoading, error, isStale } = useDCAPreview(
    {
      symbol,
      assetClass,
      strategy,
      currentPrice,
      baseOrderAmount,
      averagingOrdersAmount,
      ordersCount,
      stepPercent,
      amountMultiplier,
      amountMultiplierEnabled,
      stepMultiplier,
      stepMultiplierEnabled,
    },
    { enabled: currentPrice > 0 }
  )

  // Derive display properties
  const requiresWholeShares = assetClass === 'stock' || assetClass === 'etf'
  
  // Handle fix button click using API-provided suggested fix
  const handleFix = React.useCallback(() => {
    if (onFixConfig && data?.validation?.suggested_fix) {
      const fix = data.validation.suggested_fix
      onFixConfig(fix.orders_count, fix.step_percent ?? stepPercent)
    }
  }, [onFixConfig, data?.validation?.suggested_fix, stepPercent])

  // Loading state (only show spinner on initial load, not during stale-while-revalidate)
  if (isLoading && !data) {
    return (
      <div className="flex items-center justify-center py-8 bg-muted/30 rounded-lg">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">Loading preview...</span>
      </div>
    )
  }

  // Prompt user to enter symbol when price is not available
  if (currentPrice <= 0) {
    return (
      <div className="text-xs text-muted-foreground text-center py-4 bg-muted/30 rounded-lg">
        Enter a symbol to see order preview
      </div>
    )
  }

  // Error state
  if (error && !data) {
    return (
      <div className="flex items-start gap-2 p-3 bg-destructive/10 border border-destructive/30 rounded-lg">
        <AlertTriangle className="h-4 w-4 text-destructive mt-0.5 flex-shrink-0" />
        <div className="flex-1">
          <p className="text-sm font-medium text-destructive">Preview Error</p>
          <p className="text-xs text-muted-foreground">{error}</p>
        </div>
      </div>
    )
  }

  // No data yet (e.g., symbol not entered)
  if (!data || data.orders.length === 0) {
    return null
  }

  // Extract data from API response
  const orders = data.orders
  const totals = data.totals
  const validation = data.validation

  // Check if any orders were adjusted for whole shares
  const hasAdjustedOrders = orders.some(o => o.was_adjusted && !o.has_insufficient_shares)
  
  // Check for insufficient shares (orders that would be 0 shares)
  const ordersWithInsufficientShares = orders.filter(o => o.has_insufficient_shares)
  const hasInsufficientShares = ordersWithInsufficientShares.length > 0
  const firstInsufficientOrder = ordersWithInsufficientShares[0]
  
  // Find validation issues by type
  const errorIssues = validation.issues.filter(i => i.severity === 'error')
  const warningIssues = validation.issues.filter(i => i.severity === 'warning')
  const hasErrors = errorIssues.length > 0
  
  // Check for invalid orders (from API)
  const hasInvalidOrders = orders.some(o => o.is_invalid)
  const firstInvalidOrder = orders.find(o => o.is_invalid)

  // Use totals from API
  const totalInvestment = totals.total_investment
  const totalUnits = totals.total_units
  const maxDeviation = totals.max_deviation_pct
  const finalAveragePrice = totals.final_average_price

  return (
    <div className={`space-y-3 ${isStale ? 'opacity-70' : ''}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Label className="text-xs text-muted-foreground uppercase">Order Preview</Label>
          {(isLoading || isStale) && (
            <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
          )}
        </div>
        <span className="text-xs text-muted-foreground">
          Current: ${currentPrice.toLocaleString()}
        </span>
      </div>

      {/* Whole Shares Warning for Stocks */}
      {requiresWholeShares && hasAdjustedOrders && (
        <div className="flex items-start gap-2 p-2 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
          <Info className="h-4 w-4 text-yellow-600 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-yellow-700 dark:text-yellow-400">
            Stock orders adjusted to whole shares. Actual investment amounts may differ from configured values.
          </p>
        </div>
      )}

      {/* API Warning Issues */}
      {warningIssues.map((issue, idx) => (
        <div key={idx} className="flex items-start gap-2 p-2 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
          <Info className="h-4 w-4 text-yellow-600 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-yellow-700 dark:text-yellow-400">{issue.message}</p>
        </div>
      ))}

      {/* Validation Error Banner (from API) */}
      {hasErrors && (
        <div className="flex items-start gap-2 p-3 bg-destructive/10 border border-destructive/30 rounded-lg">
          <AlertTriangle className="h-4 w-4 text-destructive mt-0.5 flex-shrink-0" />
          <div className="flex-1 space-y-1">
            <p className="text-sm font-medium text-destructive">
              Invalid Configuration
            </p>
            {errorIssues.map((issue, idx) => (
              <p key={idx} className="text-xs text-muted-foreground">{issue.message}</p>
            ))}
            {onFixConfig && validation.suggested_fix && (
              <Button
                variant="outline"
                size="sm"
                className="mt-2 h-7 text-xs border-destructive/50 text-destructive hover:bg-destructive/10"
                onClick={handleFix}
              >
                Fix: {validation.suggested_fix.description}
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Insufficient Shares Error Banner */}
      {hasInsufficientShares && !hasErrors && (
        <div className="flex items-start gap-2 p-3 bg-destructive/10 border border-destructive/30 rounded-lg">
          <AlertTriangle className="h-4 w-4 text-destructive mt-0.5 flex-shrink-0" />
          <div className="flex-1 space-y-1">
            <p className="text-sm font-medium text-destructive">
              Insufficient Shares
            </p>
            <p className="text-xs text-muted-foreground">
              {ordersWithInsufficientShares.length === 1 
                ? `${firstInsufficientOrder?.order_label} would have 0 shares.`
                : `${ordersWithInsufficientShares.length} orders would have 0 shares.`
              }
              {' '}Increase the total shares or reduce the number of orders.
            </p>
            {onFixConfig && validation.suggested_fix && (
              <Button
                variant="outline"
                size="sm"
                className="mt-2 h-7 text-xs border-destructive/50 text-destructive hover:bg-destructive/10"
                onClick={handleFix}
              >
                Fix: {validation.suggested_fix.description}
              </Button>
            )}
          </div>
        </div>
      )}
      
      {/* Compact Table View */}
      <div className="border rounded-lg overflow-hidden">
        <div className="max-h-[240px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/50 sticky top-0">
              <tr>
                <th className="text-left py-2 px-2 font-medium text-muted-foreground">Order</th>
                <th className="text-right py-2 px-2 font-medium text-muted-foreground">
                  {requiresWholeShares ? 'Shares' : (isShort ? 'Units' : 'Amount')}
                </th>
                <th className="text-right py-2 px-2 font-medium text-muted-foreground">
                  {requiresWholeShares ? 'Amount' : (isShort ? 'Amount' : 'Price')}
                </th>
                <th className="text-right py-2 px-2 font-medium text-muted-foreground">
                  {requiresWholeShares ? 'Price' : (isShort ? 'Price' : 'Dev.')}
                </th>
                <th className="text-right py-2 px-2 font-medium text-muted-foreground">
                  {requiresWholeShares ? 'Dev.' : (isShort ? 'Dev.' : 'Avg Price')}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {orders.map((order) => (
                <tr 
                  key={order.order_number} 
                  className={
                    order.is_invalid || order.has_insufficient_shares
                      ? 'bg-destructive/10 text-destructive' 
                      : order.was_adjusted
                        ? 'bg-yellow-500/5'
                        : order.order_number === 0 
                          ? 'bg-primary/5' 
                          : 'hover:bg-muted/30'
                  }
                >
                  <td className="py-1.5 px-2">
                    <span className={
                      order.is_invalid || order.has_insufficient_shares
                        ? 'text-destructive' 
                        : order.order_number === 0 
                          ? 'font-medium text-primary' 
                          : ''
                    }>
                      {order.order_label}
                      {(order.is_invalid || order.has_insufficient_shares) && ' ⚠️'}
                      {order.was_adjusted && !order.is_invalid && !order.has_insufficient_shares && ' *'}
                    </span>
                  </td>
                  {requiresWholeShares ? (
                    // Stocks: Shares | Amount | Price | Dev
                    <>
                      <td className="py-1.5 px-2 text-right font-mono">
                        {order.is_invalid ? '—' : order.has_insufficient_shares ? <span className="text-destructive">0</span> : order.units}
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono">
                        {order.is_invalid || order.has_insufficient_shares ? '—' : `$${order.adjusted_amount.toLocaleString()}`}
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono">
                        {order.is_invalid ? (
                          <span className="text-destructive">Invalid</span>
                        ) : (
                          `$${order.target_price.toLocaleString()}`
                        )}
                      </td>
                      <td className="py-1.5 px-2 text-right">
                        {order.price_deviation_pct === 0 ? (
                          <span className="text-muted-foreground">—</span>
                        ) : order.is_invalid ? (
                          <span className="text-destructive font-medium">
                            {isShort ? '+' : '-'}{order.price_deviation_pct}%
                          </span>
                        ) : (
                          <span className={isShort ? 'text-red-500' : 'text-green-500'}>
                            {isShort ? '+' : '-'}{order.price_deviation_pct}%
                          </span>
                        )}
                      </td>
                    </>
                  ) : (
                    // Crypto/Forex: Amount | Price | Dev | Avg Price
                    <>
                      <td className="py-1.5 px-2 text-right font-mono">
                        {isShort ? (
                          order.units.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 8 })
                        ) : (
                          `$${order.amount.toLocaleString()}`
                        )}
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono">
                        {order.is_invalid ? (
                          <span className="text-destructive">Invalid</span>
                        ) : isShort ? (
                          `$${order.adjusted_amount.toLocaleString()}`
                        ) : (
                          `$${order.target_price.toLocaleString()}`
                        )}
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono">
                        {order.is_invalid ? (
                          <span className="text-destructive">Invalid</span>
                        ) : isShort ? (
                          `$${order.target_price.toLocaleString()}`
                        ) : (
                          order.price_deviation_pct === 0 ? (
                            <span className="text-muted-foreground">—</span>
                          ) : (
                            <span className="text-green-500">-{order.price_deviation_pct}%</span>
                          )
                        )}
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono text-blue-600 dark:text-blue-400">
                        {order.is_invalid ? '—' : isShort ? (
                          order.price_deviation_pct === 0 ? (
                            <span className="text-muted-foreground">—</span>
                          ) : (
                            <span className="text-red-500">+{order.price_deviation_pct}%</span>
                          )
                        ) : (
                          `$${order.average_price.toLocaleString()}`
                        )}
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Summary Stats */}
      <div className={`grid ${requiresWholeShares || isShort ? 'grid-cols-4' : 'grid-cols-3'} gap-2 text-xs`}>
        {(requiresWholeShares || isShort) && (
          <div className="bg-muted/30 rounded-lg p-2 text-center">
            <div className="text-muted-foreground">{requiresWholeShares ? 'Total Shares' : 'Total Units'}</div>
            <div className="font-medium">
              {requiresWholeShares 
                ? totalUnits 
                : totalUnits.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 8 })
              }
            </div>
          </div>
        )}
        <div className="bg-muted/30 rounded-lg p-2 text-center">
          <div className="text-muted-foreground">Total Investment</div>
          <div className="font-medium">${totalInvestment.toLocaleString()}</div>
        </div>
        <div className="bg-muted/30 rounded-lg p-2 text-center">
          <div className="text-muted-foreground">Final Avg Price</div>
          <div className="font-medium text-blue-600 dark:text-blue-400">
            ${finalAveragePrice.toLocaleString() || '—'}
          </div>
        </div>
        <div className="bg-muted/30 rounded-lg p-2 text-center">
          <div className="text-muted-foreground">Max Deviation</div>
          <div className={`font-medium ${isShort ? 'text-red-500' : 'text-green-500'}`}>
            {isShort ? '+' : '-'}{maxDeviation}%
          </div>
        </div>
      </div>
    </div>
  )
}
