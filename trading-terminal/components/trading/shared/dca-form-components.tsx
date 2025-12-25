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
import { ChevronDown, ChevronRight, Minus, Plus, AlertTriangle, Info } from 'lucide-react'
import { useDebouncedNumericInput } from '@/lib/hooks'

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
  assetClass?: 'crypto' | 'stock' | 'forex' | 'commodity' | 'etf' | 'index'
}

/** Validation result for DCA order configuration */
interface DCAValidationResult {
  isValid: boolean
  maxValidOrdersCount: number
  maxSafeDeviation: number
  invalidOrderIndex: number | null
}

interface OrderPreviewRow {
  orderNumber: number
  orderLabel: string
  amount: number
  /** Actual amount after rounding for whole shares (stocks only) */
  adjustedAmount: number
  priceDeviation: number
  targetPrice: number
  cumulativeAmount: number
  cumulativeUnits: number
  averagePrice: number
  isInvalid?: boolean
  /** Number of units/shares for this order */
  units: number
  /** Whether the order had to be adjusted for whole shares */
  wasAdjusted?: boolean
  /** Whether this order has insufficient shares (would be 0) */
  hasInsufficientShares?: boolean
}

/**
 * Validates DCA configuration to ensure no orders would result in negative prices.
 * For long positions, total deviation must stay below 100%.
 */
function validateDCAConfig({
  ordersCount,
  stepPercent,
  stepMultiplier,
  stepMultiplierEnabled,
  isShort = false,
}: {
  ordersCount: number
  stepPercent: number
  stepMultiplier: number
  stepMultiplierEnabled: boolean
  isShort?: boolean
}): DCAValidationResult {
  // Short positions don't have this constraint (price going up is fine)
  if (isShort) {
    return { isValid: true, maxValidOrdersCount: ordersCount, maxSafeDeviation: 100, invalidOrderIndex: null }
  }

  const effectiveStepMult = stepMultiplierEnabled ? stepMultiplier : 1.0
  let currentStepPercent = stepPercent
  let totalDeviation = 0
  let maxValidOrders = 0
  let invalidIndex: number | null = null

  for (let i = 0; i < ordersCount; i++) {
    if (i === 0) {
      totalDeviation = stepPercent
    } else {
      totalDeviation += currentStepPercent
      if (stepMultiplierEnabled) {
        currentStepPercent *= effectiveStepMult
      }
    }
    
    // Check if this order would result in negative/zero price (deviation >= 100%)
    if (totalDeviation >= 100) {
      invalidIndex = i
      break
    }
    maxValidOrders = i + 1
  }

  // Calculate max safe deviation (leave some buffer)
  const maxSafeDeviation = 95 // 95% max to leave some buffer

  return {
    isValid: invalidIndex === null,
    maxValidOrdersCount: maxValidOrders,
    maxSafeDeviation,
    invalidOrderIndex: invalidIndex,
  }
}

/**
 * Calculates the DCA order preview data for visualization.
 * Shows investment per order, average price, and price deviation.
 * Marks orders as invalid if they would result in negative prices.
 * For stocks, adjusts amounts to buy whole shares only.
 */
function calculateDCAOrders({
  baseOrderAmount,
  averagingOrdersAmount,
  ordersCount,
  stepPercent,
  amountMultiplier,
  amountMultiplierEnabled,
  stepMultiplier,
  stepMultiplierEnabled,
  currentPrice,
  isShort = false,
  assetClass = 'crypto',
}: Omit<DCAOrderPreviewProps, 'currency' | 'onFixConfig'>): OrderPreviewRow[] {
  const orders: OrderPreviewRow[] = []
  
  if (currentPrice <= 0 || ordersCount < 1) {
    return orders
  }

  // Determine if we need whole shares (stocks/etf only - not crypto)
  const requiresWholeShares = assetClass === 'stock' || assetClass === 'etf'

  // Calculate individual averaging order amounts
  const effectiveAmountMult = amountMultiplierEnabled ? amountMultiplier : 1.0
  const effectiveStepMult = stepMultiplierEnabled ? stepMultiplier : 1.0
  
  // Calculate the first averaging order amount and total weighted sum
  // If multiplier enabled: amounts are baseAmt, baseAmt*mult, baseAmt*mult^2, ...
  // Total = baseAmt * (1 + mult + mult^2 + ... + mult^(n-1))
  let totalMultiplierWeight = 0
  for (let i = 0; i < ordersCount; i++) {
    totalMultiplierWeight += Math.pow(effectiveAmountMult, i)
  }
  const firstAvgOrderAmount = totalMultiplierWeight > 0 
    ? averagingOrdersAmount / totalMultiplierWeight 
    : averagingOrdersAmount / ordersCount

  // Track cumulative values
  let cumulativeAmount = 0
  let cumulativeUnits = 0
  let currentStepPercent = stepPercent
  let currentDeviation = 0

  // For stocks:
  // - Long: input is USD, need to calculate shares
  // - Short: input is already in shares/units (base currency) for ALL asset types
  const inputIsUnits = isShort

  // Base Order (Order #0)
  let baseUnits: number
  let adjustedBaseAmount: number
  let baseWasAdjusted = false
  let baseHasInsufficientShares = false
  
  if (inputIsUnits) {
    // Short positions: input is units (shares for stocks, coins for crypto)
    const rawUnits = baseOrderAmount
    if (requiresWholeShares) {
      // Stocks: round to whole shares
      baseUnits = Math.round(rawUnits)
      // Mark as insufficient if rounds to 0
      if (baseUnits < 1 && rawUnits > 0) {
        baseHasInsufficientShares = true
        baseUnits = 0
      }
      baseWasAdjusted = baseUnits !== rawUnits
    } else {
      // Crypto/forex: keep fractional units as-is
      baseUnits = rawUnits
    }
    adjustedBaseAmount = baseUnits * currentPrice
  } else if (requiresWholeShares && currentPrice > 0) {
    // Long stocks: input is USD, calculate shares and round
    const rawUnits = baseOrderAmount / currentPrice
    baseUnits = Math.round(rawUnits)
    // Mark as insufficient if rounds to 0
    if (baseUnits < 1 && rawUnits > 0) {
      baseHasInsufficientShares = true
      baseUnits = 0
    }
    adjustedBaseAmount = baseUnits * currentPrice
    baseWasAdjusted = baseUnits !== rawUnits
  } else {
    // Long crypto/forex: input is USD, calculate units
    baseUnits = currentPrice > 0 ? baseOrderAmount / currentPrice : 0
    adjustedBaseAmount = baseOrderAmount
  }
  
  cumulativeAmount = adjustedBaseAmount
  cumulativeUnits = baseUnits
  
  orders.push({
    orderNumber: 0,
    orderLabel: 'Base Order',
    amount: baseOrderAmount,
    adjustedAmount: Math.round(adjustedBaseAmount * 100) / 100,
    priceDeviation: 0,
    targetPrice: currentPrice,
    cumulativeAmount: Math.round(cumulativeAmount * 100) / 100,
    cumulativeUnits: Math.round(cumulativeUnits * 10000) / 10000,
    averagePrice: currentPrice,
    isInvalid: false,
    units: baseUnits,
    wasAdjusted: baseWasAdjusted,
    hasInsufficientShares: baseHasInsufficientShares,
  })

  // Averaging Orders (Safety Orders)
  let currentOrderAmount = firstAvgOrderAmount
  
  for (let i = 0; i < ordersCount; i++) {
    // Calculate deviation for this order
    if (i === 0) {
      currentDeviation = stepPercent
    } else {
      currentDeviation += currentStepPercent
      if (stepMultiplierEnabled) {
        currentStepPercent *= effectiveStepMult
      }
    }
    
    // Check if deviation would result in invalid price (for long positions)
    const isInvalidOrder = !isShort && currentDeviation >= 100
    
    // Calculate target price (down for long, up for short)
    const priceMultiplier = isShort 
      ? (1 + currentDeviation / 100) 
      : (1 - currentDeviation / 100)
    const targetPrice = Math.max(0, currentPrice * priceMultiplier)
    
    // Calculate units and amount based on input type
    let units: number
    let adjustedAmount: number
    let wasAdjusted = false
    let hasInsufficientShares = false
    
    if (inputIsUnits) {
      // Short positions: input is units (shares for stocks, coins for crypto)
      const rawUnits = currentOrderAmount
      if (requiresWholeShares) {
        // Stocks: round to whole shares
        units = Math.round(rawUnits)
        // Mark as insufficient if rounds to 0
        if (units < 1 && rawUnits > 0) {
          hasInsufficientShares = true
          units = 0
        }
        wasAdjusted = units !== rawUnits
      } else {
        // Crypto/forex: keep fractional units as-is
        units = rawUnits
      }
      adjustedAmount = units * targetPrice
    } else if (requiresWholeShares && targetPrice > 0 && !isInvalidOrder) {
      // Long stocks: input is USD, calculate shares and round
      const rawUnits = currentOrderAmount / targetPrice
      units = Math.round(rawUnits)
      // Mark as insufficient if rounds to 0
      if (units < 1 && rawUnits > 0) {
        hasInsufficientShares = true
        units = 0
      }
      adjustedAmount = units * targetPrice
      wasAdjusted = units !== rawUnits
    } else {
      // Long crypto/forex: input is USD, calculate units
      units = targetPrice > 0 ? currentOrderAmount / targetPrice : 0
      adjustedAmount = currentOrderAmount
    }
    
    // Update cumulative values
    cumulativeAmount += adjustedAmount
    cumulativeUnits += units
    
    // Calculate new average price
    const averagePrice = cumulativeUnits > 0 ? cumulativeAmount / cumulativeUnits : 0
    
    orders.push({
      orderNumber: i + 1,
      orderLabel: `SO ${i + 1}`,
      amount: Math.round(currentOrderAmount * 100) / 100,
      adjustedAmount: Math.round(adjustedAmount * 100) / 100,
      priceDeviation: Math.round(currentDeviation * 100) / 100,
      targetPrice: Math.round(targetPrice * 100) / 100,
      cumulativeAmount: Math.round(cumulativeAmount * 100) / 100,
      cumulativeUnits: Math.round(cumulativeUnits * 10000) / 10000,
      averagePrice: Math.round(averagePrice * 100) / 100,
      isInvalid: isInvalidOrder,
      units: units,
      wasAdjusted: wasAdjusted,
      hasInsufficientShares: hasInsufficientShares,
    })
    
    // Apply amount multiplier for next order
    if (amountMultiplierEnabled) {
      currentOrderAmount *= effectiveAmountMult
    }
  }
  
  return orders
}

/**
 * DCA Order Preview Table Component.
 * Displays a visual breakdown of all DCA orders showing:
 * - Investment amount per order
 * - Target price and deviation from current price
 * - Running average price after each order
 * 
 * Shows validation errors when configuration would result in negative prices.
 * 
 * @example
 * ```tsx
 * <DCAOrderPreview
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
  const orders = React.useMemo(
    () => calculateDCAOrders({
      baseOrderAmount,
      averagingOrdersAmount,
      ordersCount,
      stepPercent,
      amountMultiplier,
      amountMultiplierEnabled,
      stepMultiplier,
      stepMultiplierEnabled,
      currentPrice,
      isShort,
      assetClass,
    }),
    [
      baseOrderAmount,
      averagingOrdersAmount,
      ordersCount,
      stepPercent,
      amountMultiplier,
      amountMultiplierEnabled,
      stepMultiplier,
      stepMultiplierEnabled,
      currentPrice,
      isShort,
      assetClass,
    ]
  )

  // Check if any orders were adjusted for whole shares
  const hasAdjustedOrders = orders.some(o => o.wasAdjusted && !o.hasInsufficientShares)
  const requiresWholeShares = assetClass === 'stock' || assetClass === 'etf'
  
  // Check for insufficient shares (orders that would be 0 shares)
  const ordersWithInsufficientShares = orders.filter(o => o.hasInsufficientShares)
  const hasInsufficientShares = ordersWithInsufficientShares.length > 0
  const firstInsufficientOrder = ordersWithInsufficientShares[0]
  
  // Calculate max valid orders count for insufficient shares fix
  // Count how many orders have at least 1 share
  const maxOrdersWithShares = orders.filter(o => o.units >= 1 && o.orderNumber > 0).length

  // For stocks with share input (short), check if total shares exceed budget
  const inputIsShares = requiresWholeShares && isShort
  const configuredTotalShares = inputIsShares ? baseOrderAmount + averagingOrdersAmount : 0
  const actualTotalShares = orders.reduce((sum, o) => sum + o.units, 0)
  const hasOverAllocation = inputIsShares && actualTotalShares > configuredTotalShares
  const overAllocationAmount = actualTotalShares - configuredTotalShares
  
  // Find max orders that fit within budget
  const findMaxOrdersWithinBudget = React.useCallback(() => {
    if (!inputIsShares) return ordersCount
    
    // Try reducing orders until we fit within budget
    for (let tryCount = ordersCount - 1; tryCount >= 1; tryCount--) {
      // Recalculate with fewer orders
      const effectiveAmountMult = amountMultiplierEnabled ? amountMultiplier : 1.0
      let totalWeight = 0
      for (let i = 0; i < tryCount; i++) {
        totalWeight += Math.pow(effectiveAmountMult, i)
      }
      const firstOrderShares = totalWeight > 0 ? averagingOrdersAmount / totalWeight : averagingOrdersAmount / tryCount
      
      let totalShares = Math.round(baseOrderAmount) // Base order
      let currentShares = firstOrderShares
      for (let i = 0; i < tryCount; i++) {
        totalShares += Math.round(currentShares)
        if (amountMultiplierEnabled) {
          currentShares *= effectiveAmountMult
        }
      }
      
      if (totalShares <= configuredTotalShares) {
        return tryCount
      }
    }
    return 0
  }, [inputIsShares, ordersCount, baseOrderAmount, averagingOrdersAmount, amountMultiplier, amountMultiplierEnabled, configuredTotalShares])
  
  const maxOrdersWithinBudget = React.useMemo(() => findMaxOrdersWithinBudget(), [findMaxOrdersWithinBudget])

  // Validate configuration
  const validation = React.useMemo(
    () => validateDCAConfig({
      ordersCount,
      stepPercent,
      stepMultiplier,
      stepMultiplierEnabled,
      isShort,
    }),
    [ordersCount, stepPercent, stepMultiplier, stepMultiplierEnabled, isShort]
  )

  // Handle fix button click for negative price issue
  const handleFix = React.useCallback(() => {
    if (onFixConfig && validation.maxValidOrdersCount > 0) {
      onFixConfig(validation.maxValidOrdersCount, stepPercent)
    }
  }, [onFixConfig, validation.maxValidOrdersCount, stepPercent])
  
  // Handle fix button click for insufficient shares
  const handleFixInsufficientShares = React.useCallback(() => {
    if (onFixConfig && maxOrdersWithShares > 0) {
      onFixConfig(maxOrdersWithShares, stepPercent)
    }
  }, [onFixConfig, maxOrdersWithShares, stepPercent])
  
  // Handle fix button click for over-allocation
  const handleFixOverAllocation = React.useCallback(() => {
    if (onFixConfig && maxOrdersWithinBudget > 0) {
      onFixConfig(maxOrdersWithinBudget, stepPercent)
    }
  }, [onFixConfig, maxOrdersWithinBudget, stepPercent])

  if (currentPrice <= 0) {
    return (
      <div className="text-xs text-muted-foreground text-center py-4 bg-muted/30 rounded-lg">
        Enter a symbol to see order preview
      </div>
    )
  }

  if (orders.length === 0) {
    return null
  }

  // Check for invalid orders
  const hasInvalidOrders = orders.some(o => o.isInvalid)
  const firstInvalidOrder = orders.find(o => o.isInvalid)

  // Calculate totals (only for valid orders, use adjusted amounts for stocks and crypto shorts)
  const validOrders = orders.filter(o => !o.isInvalid)
  // For crypto/forex shorts, input is in units so adjustedAmount has the USD value
  // For crypto/forex longs, input is in USD so amount has the USD value
  const inputIsUnits = isShort && !requiresWholeShares
  const totalInvestment = requiresWholeShares || inputIsUnits
    ? validOrders.reduce((sum, o) => sum + o.adjustedAmount, 0)
    : validOrders.reduce((sum, o) => sum + o.amount, 0)
  const totalUnits = validOrders.reduce((sum, o) => sum + o.units, 0)
  const lastValidOrder = validOrders[validOrders.length - 1]
  const maxDeviation = lastValidOrder?.priceDeviation || 0

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Label className="text-xs text-muted-foreground uppercase">Order Preview</Label>
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

      {/* Validation Error Banner */}
      {hasInvalidOrders && (
        <div className="flex items-start gap-2 p-3 bg-destructive/10 border border-destructive/30 rounded-lg">
          <AlertTriangle className="h-4 w-4 text-destructive mt-0.5 flex-shrink-0" />
          <div className="flex-1 space-y-1">
            <p className="text-sm font-medium text-destructive">
              Invalid Configuration
            </p>
            <p className="text-xs text-muted-foreground">
              Order {firstInvalidOrder?.orderNumber} would have a price deviation of {firstInvalidOrder?.priceDeviation}% 
              which results in a negative price. Maximum allowed deviation is 100%.
            </p>
            {onFixConfig && validation.maxValidOrdersCount > 0 && (
              <Button
                variant="outline"
                size="sm"
                className="mt-2 h-7 text-xs border-destructive/50 text-destructive hover:bg-destructive/10"
                onClick={handleFix}
              >
                Fix: Reduce to {validation.maxValidOrdersCount} orders
              </Button>
            )}
            {onFixConfig && validation.maxValidOrdersCount === 0 && (
              <p className="text-xs text-destructive mt-1">
                Try reducing the step percentage or disabling the step multiplier.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Insufficient Shares Error Banner */}
      {hasInsufficientShares && !hasInvalidOrders && (
        <div className="flex items-start gap-2 p-3 bg-destructive/10 border border-destructive/30 rounded-lg">
          <AlertTriangle className="h-4 w-4 text-destructive mt-0.5 flex-shrink-0" />
          <div className="flex-1 space-y-1">
            <p className="text-sm font-medium text-destructive">
              Insufficient Shares
            </p>
            <p className="text-xs text-muted-foreground">
              {ordersWithInsufficientShares.length === 1 
                ? `${firstInsufficientOrder?.orderLabel} would have 0 shares.`
                : `${ordersWithInsufficientShares.length} orders would have 0 shares (${ordersWithInsufficientShares.map(o => o.orderLabel).join(', ')}).`
              }
              {' '}Increase the total shares or reduce the number of orders.
            </p>
            {onFixConfig && maxOrdersWithShares > 0 && (
              <Button
                variant="outline"
                size="sm"
                className="mt-2 h-7 text-xs border-destructive/50 text-destructive hover:bg-destructive/10"
                onClick={handleFixInsufficientShares}
              >
                Fix: Reduce to {maxOrdersWithShares} orders
              </Button>
            )}
            {maxOrdersWithShares === 0 && (
              <p className="text-xs text-destructive mt-1">
                Increase the averaging orders quantity to at least {ordersCount} shares.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Over-Allocation Error Banner (for short stocks) */}
      {hasOverAllocation && !hasInvalidOrders && !hasInsufficientShares && (
        <div className="flex items-start gap-2 p-3 bg-destructive/10 border border-destructive/30 rounded-lg">
          <AlertTriangle className="h-4 w-4 text-destructive mt-0.5 flex-shrink-0" />
          <div className="flex-1 space-y-1">
            <p className="text-sm font-medium text-destructive">
              Exceeds Share Budget
            </p>
            <p className="text-xs text-muted-foreground">
              Rounding to whole shares results in {actualTotalShares} shares, 
              but only {configuredTotalShares} shares are configured ({overAllocationAmount} over budget).
              Reduce the number of orders or increase the total shares.
            </p>
            {onFixConfig && maxOrdersWithinBudget > 0 && (
              <Button
                variant="outline"
                size="sm"
                className="mt-2 h-7 text-xs border-destructive/50 text-destructive hover:bg-destructive/10"
                onClick={handleFixOverAllocation}
              >
                Fix: Reduce to {maxOrdersWithinBudget} orders
              </Button>
            )}
            {maxOrdersWithinBudget === 0 && (
              <p className="text-xs text-destructive mt-1">
                Increase the total shares to at least {actualTotalShares}.
              </p>
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
                  key={order.orderNumber} 
                  className={
                    order.isInvalid || order.hasInsufficientShares
                      ? 'bg-destructive/10 text-destructive' 
                      : order.wasAdjusted
                        ? 'bg-yellow-500/5'
                        : order.orderNumber === 0 
                          ? 'bg-primary/5' 
                          : 'hover:bg-muted/30'
                  }
                >
                  <td className="py-1.5 px-2">
                    <span className={
                      order.isInvalid || order.hasInsufficientShares
                        ? 'text-destructive' 
                        : order.orderNumber === 0 
                          ? 'font-medium text-primary' 
                          : ''
                    }>
                      {order.orderLabel}
                      {(order.isInvalid || order.hasInsufficientShares) && ' ⚠️'}
                      {order.wasAdjusted && !order.isInvalid && !order.hasInsufficientShares && ' *'}
                    </span>
                  </td>
                  {requiresWholeShares ? (
                    // Stocks: Shares | Amount | Price | Dev
                    <>
                      <td className="py-1.5 px-2 text-right font-mono">
                        {order.isInvalid ? '—' : order.hasInsufficientShares ? <span className="text-destructive">0</span> : order.units}
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono">
                        {order.isInvalid || order.hasInsufficientShares ? '—' : `$${order.adjustedAmount.toLocaleString()}`}
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono">
                        {order.isInvalid ? (
                          <span className="text-destructive">Invalid</span>
                        ) : (
                          `$${order.targetPrice.toLocaleString()}`
                        )}
                      </td>
                      <td className="py-1.5 px-2 text-right">
                        {order.priceDeviation === 0 ? (
                          <span className="text-muted-foreground">—</span>
                        ) : order.isInvalid ? (
                          <span className="text-destructive font-medium">
                            {isShort ? '+' : '-'}{order.priceDeviation}%
                          </span>
                        ) : (
                          <span className={isShort ? 'text-red-500' : 'text-green-500'}>
                            {isShort ? '+' : '-'}{order.priceDeviation}%
                          </span>
                        )}
                      </td>
                    </>
                  ) : (
                    // Crypto/Forex: Amount | Price | Dev | Avg Price
                    // For shorts: input is in units, show units in Amount column
                    // For longs: input is USD, show USD in Amount column
                    <>
                      <td className="py-1.5 px-2 text-right font-mono">
                        {isShort ? (
                          // Short: show units (e.g., 0.0286 BTC)
                          order.units.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 8 })
                        ) : (
                          // Long: show USD amount
                          `$${order.amount.toLocaleString()}`
                        )}
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono">
                        {order.isInvalid ? (
                          <span className="text-destructive">Invalid</span>
                        ) : isShort ? (
                          // Short: show USD value (units * price)
                          `$${order.adjustedAmount.toLocaleString()}`
                        ) : (
                          // Long: show price
                          `$${order.targetPrice.toLocaleString()}`
                        )}
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono">
                        {order.isInvalid ? (
                          <span className="text-destructive">Invalid</span>
                        ) : isShort ? (
                          // Short: show price in third column
                          `$${order.targetPrice.toLocaleString()}`
                        ) : (
                          // Long: show deviation
                          order.priceDeviation === 0 ? (
                            <span className="text-muted-foreground">—</span>
                          ) : (
                            <span className="text-green-500">-{order.priceDeviation}%</span>
                          )
                        )}
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono text-blue-600 dark:text-blue-400">
                        {order.isInvalid ? '—' : isShort ? (
                          // Short: show deviation in fourth column
                          order.priceDeviation === 0 ? (
                            <span className="text-muted-foreground">—</span>
                          ) : (
                            <span className="text-red-500">+{order.priceDeviation}%</span>
                          )
                        ) : (
                          // Long: show avg price
                          `$${order.averagePrice.toLocaleString()}`
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
            ${lastValidOrder?.averagePrice.toLocaleString() || '—'}
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
