/**
 * Configuration Editor Component
 * 
 * Professional configuration interface for DCA strategy settings,
 * risk limits, and trading parameters with validation and save.
 * 
 * @module components/trading/config-editor
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
import { Slider } from '@/components/ui/slider'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import {
  Save,
  RotateCcw,
  AlertTriangle,
  CheckCircle,
  Shield,
  TrendingUp,
  DollarSign,
  Percent,
  Layers,
  Clock,
  Target,
} from 'lucide-react'

export interface DCAConfig {
  enabled: boolean
  maxLayers: number
  layerMultiplier: number
  dropPercentTrigger: number
  minLayerInterval: number
  maxPositionSize: number
}

export interface RiskConfig {
  maxPositionPercent: number
  maxDailyLoss: number
  maxOpenPositions: number
  stopLossPercent: number
  takeProfitPercent: number
  enableStopLoss: boolean
  enableTakeProfit: boolean
}

export interface TradingConfig {
  defaultOrderType: 'market' | 'limit'
  slippageTolerance: number
  extendedHoursTrading: boolean
  paperTrading: boolean
  confirmOrders: boolean
  autoCloseEOD: boolean
}

export interface ConfigState {
  dca: DCAConfig
  risk: RiskConfig
  trading: TradingConfig
}

interface ConfigEditorProps {
  config: ConfigState
  onSave: (config: ConfigState) => Promise<void>
  onReset: () => void
  isLoading?: boolean
  hasUnsavedChanges?: boolean
}

const defaultConfig: ConfigState = {
  dca: {
    enabled: true,
    maxLayers: 5,
    layerMultiplier: 1.5,
    dropPercentTrigger: 5,
    minLayerInterval: 300,
    maxPositionSize: 10000,
  },
  risk: {
    maxPositionPercent: 10,
    maxDailyLoss: 1000,
    maxOpenPositions: 5,
    stopLossPercent: 10,
    takeProfitPercent: 20,
    enableStopLoss: true,
    enableTakeProfit: false,
  },
  trading: {
    defaultOrderType: 'market',
    slippageTolerance: 0.5,
    extendedHoursTrading: false,
    paperTrading: false,
    confirmOrders: true,
    autoCloseEOD: false,
  },
}

/**
 * Number Input with Slider Component
 */
function SliderInput({
  label,
  description,
  value,
  onChange,
  min,
  max,
  step,
  unit,
  icon,
}: {
  label: string
  description?: string
  value: number
  onChange: (value: number) => void
  min: number
  max: number
  step: number
  unit?: string
  icon?: React.ReactNode
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {icon}
          <div>
            <Label className="text-base">{label}</Label>
            {description && <p className="text-sm text-muted-foreground">{description}</p>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Input
            type="number"
            value={value}
            onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
            min={min}
            max={max}
            step={step}
            className="w-24 text-right"
          />
          {unit && <span className="text-sm text-muted-foreground w-8">{unit}</span>}
        </div>
      </div>
      <Slider
        value={[value]}
        onValueChange={([v]) => onChange(v)}
        min={min}
        max={max}
        step={step}
        className="w-full"
      />
    </div>
  )
}

/**
 * Toggle Setting Component
 */
function ToggleSetting({
  label,
  description,
  checked,
  onCheckedChange,
  icon,
  danger,
}: {
  label: string
  description?: string
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  icon?: React.ReactNode
  danger?: boolean
}) {
  return (
    <div className="flex items-center justify-between py-2">
      <div className="flex items-center gap-3">
        {icon && <div className={cn('text-muted-foreground', danger && 'text-loss')}>{icon}</div>}
        <div>
          <Label className={cn('text-base', danger && 'text-loss')}>{label}</Label>
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
        </div>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  )
}

/**
 * Configuration Editor Component
 * 
 * @param {ConfigEditorProps} props - Component props
 * @returns {JSX.Element} Configuration editor
 */
export function ConfigEditor({
  config: initialConfig,
  onSave,
  onReset,
  isLoading = false,
  hasUnsavedChanges = false,
}: ConfigEditorProps): JSX.Element {
  const [config, setConfig] = useState<ConfigState>(initialConfig)
  const [activeTab, setActiveTab] = useState('dca')

  const updateDCA = useCallback(<K extends keyof DCAConfig>(key: K, value: DCAConfig[K]) => {
    setConfig((prev) => ({
      ...prev,
      dca: { ...prev.dca, [key]: value },
    }))
  }, [])

  const updateRisk = useCallback(<K extends keyof RiskConfig>(key: K, value: RiskConfig[K]) => {
    setConfig((prev) => ({
      ...prev,
      risk: { ...prev.risk, [key]: value },
    }))
  }, [])

  const updateTrading = useCallback(
    <K extends keyof TradingConfig>(key: K, value: TradingConfig[K]) => {
      setConfig((prev) => ({
        ...prev,
        trading: { ...prev.trading, [key]: value },
      }))
    },
    []
  )

  const handleSave = async () => {
    await onSave(config)
  }

  const handleReset = () => {
    setConfig(initialConfig)
    onReset()
  }

  return (
    <div className="space-y-6">
      {/* Header with Actions */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Configuration</h2>
          <p className="text-muted-foreground">
            Manage DCA strategy, risk limits, and trading settings
          </p>
        </div>
        <div className="flex items-center gap-2">
          {hasUnsavedChanges && (
            <Badge variant="warning" className="mr-2">
              Unsaved Changes
            </Badge>
          )}
          <Button variant="outline" onClick={handleReset} disabled={isLoading}>
            <RotateCcw className="mr-2 h-4 w-4" />
            Reset
          </Button>
          <Button onClick={handleSave} loading={isLoading}>
            <Save className="mr-2 h-4 w-4" />
            Save Changes
          </Button>
        </div>
      </div>

      {/* Configuration Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="dca" className="gap-2">
            <Layers className="h-4 w-4" />
            DCA Strategy
          </TabsTrigger>
          <TabsTrigger value="risk" className="gap-2">
            <Shield className="h-4 w-4" />
            Risk Limits
          </TabsTrigger>
          <TabsTrigger value="trading" className="gap-2">
            <TrendingUp className="h-4 w-4" />
            Trading
          </TabsTrigger>
        </TabsList>

        {/* DCA Configuration */}
        <TabsContent value="dca" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Layers className="h-5 w-5 text-primary" />
                DCA Strategy Settings
              </CardTitle>
              <CardDescription>
                Configure Dollar Cost Averaging parameters for position building
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <ToggleSetting
                label="Enable DCA"
                description="Automatically add to positions when price drops"
                checked={config.dca.enabled}
                onCheckedChange={(v) => updateDCA('enabled', v)}
                icon={<Layers className="h-5 w-5" />}
              />

              <Separator />

              <SliderInput
                label="Maximum Layers"
                description="Maximum number of DCA layers per position"
                value={config.dca.maxLayers}
                onChange={(v) => updateDCA('maxLayers', v)}
                min={1}
                max={10}
                step={1}
                icon={<Layers className="h-5 w-5 text-muted-foreground" />}
              />

              <SliderInput
                label="Layer Multiplier"
                description="Size multiplier for each subsequent layer"
                value={config.dca.layerMultiplier}
                onChange={(v) => updateDCA('layerMultiplier', v)}
                min={1}
                max={3}
                step={0.1}
                unit="x"
                icon={<TrendingUp className="h-5 w-5 text-muted-foreground" />}
              />

              <SliderInput
                label="Drop Trigger"
                description="Price drop percentage to trigger new layer"
                value={config.dca.dropPercentTrigger}
                onChange={(v) => updateDCA('dropPercentTrigger', v)}
                min={1}
                max={20}
                step={0.5}
                unit="%"
                icon={<Percent className="h-5 w-5 text-muted-foreground" />}
              />

              <SliderInput
                label="Minimum Interval"
                description="Minimum seconds between layers"
                value={config.dca.minLayerInterval}
                onChange={(v) => updateDCA('minLayerInterval', v)}
                min={60}
                max={3600}
                step={60}
                unit="sec"
                icon={<Clock className="h-5 w-5 text-muted-foreground" />}
              />

              <SliderInput
                label="Max Position Size"
                description="Maximum total position value"
                value={config.dca.maxPositionSize}
                onChange={(v) => updateDCA('maxPositionSize', v)}
                min={1000}
                max={100000}
                step={1000}
                unit="$"
                icon={<DollarSign className="h-5 w-5 text-muted-foreground" />}
              />
            </CardContent>
          </Card>
        </TabsContent>

        {/* Risk Configuration */}
        <TabsContent value="risk" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shield className="h-5 w-5 text-primary" />
                Risk Management
              </CardTitle>
              <CardDescription>
                Set position limits and loss prevention parameters
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <SliderInput
                label="Max Position %"
                description="Maximum % of portfolio per position"
                value={config.risk.maxPositionPercent}
                onChange={(v) => updateRisk('maxPositionPercent', v)}
                min={1}
                max={50}
                step={1}
                unit="%"
                icon={<Percent className="h-5 w-5 text-muted-foreground" />}
              />

              <SliderInput
                label="Max Daily Loss"
                description="Stop trading when daily loss exceeds"
                value={config.risk.maxDailyLoss}
                onChange={(v) => updateRisk('maxDailyLoss', v)}
                min={100}
                max={10000}
                step={100}
                unit="$"
                icon={<AlertTriangle className="h-5 w-5 text-muted-foreground" />}
              />

              <SliderInput
                label="Max Open Positions"
                description="Maximum concurrent open positions"
                value={config.risk.maxOpenPositions}
                onChange={(v) => updateRisk('maxOpenPositions', v)}
                min={1}
                max={20}
                step={1}
                icon={<Layers className="h-5 w-5 text-muted-foreground" />}
              />

              <Separator />

              <ToggleSetting
                label="Enable Stop Loss"
                description="Automatically close positions at loss limit"
                checked={config.risk.enableStopLoss}
                onCheckedChange={(v) => updateRisk('enableStopLoss', v)}
                icon={<Shield className="h-5 w-5" />}
                danger
              />

              {config.risk.enableStopLoss && (
                <SliderInput
                  label="Stop Loss %"
                  description="Close position when loss exceeds"
                  value={config.risk.stopLossPercent}
                  onChange={(v) => updateRisk('stopLossPercent', v)}
                  min={1}
                  max={50}
                  step={1}
                  unit="%"
                  icon={<AlertTriangle className="h-5 w-5 text-loss" />}
                />
              )}

              <ToggleSetting
                label="Enable Take Profit"
                description="Automatically close positions at profit target"
                checked={config.risk.enableTakeProfit}
                onCheckedChange={(v) => updateRisk('enableTakeProfit', v)}
                icon={<Target className="h-5 w-5" />}
              />

              {config.risk.enableTakeProfit && (
                <SliderInput
                  label="Take Profit %"
                  description="Close position when profit reaches"
                  value={config.risk.takeProfitPercent}
                  onChange={(v) => updateRisk('takeProfitPercent', v)}
                  min={1}
                  max={100}
                  step={1}
                  unit="%"
                  icon={<CheckCircle className="h-5 w-5 text-profit" />}
                />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Trading Configuration */}
        <TabsContent value="trading" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5 text-primary" />
                Trading Settings
              </CardTitle>
              <CardDescription>Configure general trading behavior and preferences</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <Label>Default Order Type</Label>
                <Select
                  value={config.trading.defaultOrderType}
                  onValueChange={(v) => updateTrading('defaultOrderType', v as 'market' | 'limit')}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="market">Market Order</SelectItem>
                    <SelectItem value="limit">Limit Order</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <SliderInput
                label="Slippage Tolerance"
                description="Maximum acceptable price slippage"
                value={config.trading.slippageTolerance}
                onChange={(v) => updateTrading('slippageTolerance', v)}
                min={0.1}
                max={5}
                step={0.1}
                unit="%"
                icon={<Percent className="h-5 w-5 text-muted-foreground" />}
              />

              <Separator />

              <ToggleSetting
                label="Extended Hours Trading"
                description="Allow trading during pre/post market"
                checked={config.trading.extendedHoursTrading}
                onCheckedChange={(v) => updateTrading('extendedHoursTrading', v)}
                icon={<Clock className="h-5 w-5" />}
              />

              <ToggleSetting
                label="Paper Trading"
                description="Simulate trades without real execution"
                checked={config.trading.paperTrading}
                onCheckedChange={(v) => updateTrading('paperTrading', v)}
                icon={<TrendingUp className="h-5 w-5" />}
              />

              <ToggleSetting
                label="Confirm Orders"
                description="Show confirmation before placing orders"
                checked={config.trading.confirmOrders}
                onCheckedChange={(v) => updateTrading('confirmOrders', v)}
                icon={<CheckCircle className="h-5 w-5" />}
              />

              <ToggleSetting
                label="Auto-Close EOD"
                description="Close all positions at end of day"
                checked={config.trading.autoCloseEOD}
                onCheckedChange={(v) => updateTrading('autoCloseEOD', v)}
                icon={<Clock className="h-5 w-5" />}
                danger
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}

export default ConfigEditor
