/**
 * Bot Controls Panel Component
 * 
 * Interface for controlling the trading bot - start, stop, pause, and monitor status.
 * Provides real-time feedback and emergency controls.
 * 
 * @module components/trading/bot-controls
 */

'use client'

import React, { useState, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  Play,
  Pause,
  Square,
  AlertTriangle,
  Activity,
  RefreshCw,
  Shield,
  Zap,
  Clock,
  Server,
  Wifi,
  WifiOff,
  CheckCircle,
  XCircle,
  AlertCircle,
} from 'lucide-react'

export type BotStatus = 'running' | 'paused' | 'stopped' | 'error' | 'starting' | 'stopping'

interface BotStatusInfo {
  status: BotStatus
  uptime: string
  lastSignal: string
  activePositions: number
  pendingOrders: number
  todayTrades: number
  todayPnL: number
  errorMessage?: string
  isConnected: boolean
  signalrConnected: boolean
}

interface BotControlsProps {
  status: BotStatusInfo
  onStart: () => Promise<void>
  onPause: () => Promise<void>
  onStop: () => Promise<void>
  onEmergencyStop: () => Promise<void>
  onRestart: () => Promise<void>
  isLoading?: boolean
}

const statusConfig: Record<
  BotStatus,
  { label: string; color: string; icon: React.ReactNode; bgColor: string }
> = {
  running: {
    label: 'Running',
    color: 'text-profit',
    icon: <CheckCircle className="h-5 w-5" />,
    bgColor: 'bg-profit/10',
  },
  paused: {
    label: 'Paused',
    color: 'text-warning',
    icon: <Pause className="h-5 w-5" />,
    bgColor: 'bg-warning/10',
  },
  stopped: {
    label: 'Stopped',
    color: 'text-muted-foreground',
    icon: <Square className="h-5 w-5" />,
    bgColor: 'bg-muted',
  },
  error: {
    label: 'Error',
    color: 'text-loss',
    icon: <XCircle className="h-5 w-5" />,
    bgColor: 'bg-loss/10',
  },
  starting: {
    label: 'Starting...',
    color: 'text-primary',
    icon: <RefreshCw className="h-5 w-5 animate-spin" />,
    bgColor: 'bg-primary/10',
  },
  stopping: {
    label: 'Stopping...',
    color: 'text-warning',
    icon: <RefreshCw className="h-5 w-5 animate-spin" />,
    bgColor: 'bg-warning/10',
  },
}

/**
 * Status Indicator Badge
 */
function StatusBadge({ status }: { status: BotStatus }) {
  const config = statusConfig[status]
  return (
    <div className={cn('flex items-center gap-2 px-3 py-1.5 rounded-full', config.bgColor)}>
      <span className={config.color}>{config.icon}</span>
      <span className={cn('font-semibold', config.color)}>{config.label}</span>
    </div>
  )
}

/**
 * Metric Card Component
 */
function MetricCard({
  label,
  value,
  icon,
  trend,
  className,
}: {
  label: string
  value: string | number
  icon: React.ReactNode
  trend?: 'up' | 'down' | 'neutral'
  className?: string
}) {
  return (
    <div className={cn('flex items-center gap-3 p-4 rounded-lg bg-muted/30', className)}>
      <div className="p-2 rounded-lg bg-primary/10 text-primary">{icon}</div>
      <div>
        <p className="text-sm text-muted-foreground">{label}</p>
        <p
          className={cn(
            'text-lg font-bold',
            trend === 'up' && 'text-profit',
            trend === 'down' && 'text-loss'
          )}
        >
          {value}
        </p>
      </div>
    </div>
  )
}

/**
 * Emergency Stop Dialog Component
 */
function EmergencyStopDialog({
  onConfirm,
  isLoading,
}: {
  onConfirm: () => void
  isLoading: boolean
}) {
  const [isOpen, setIsOpen] = useState(false)

  const handleConfirm = () => {
    onConfirm()
    setIsOpen(false)
  }

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button variant="destructive" className="h-14 gap-2 shadow-lg" size="lg">
          <AlertTriangle className="h-5 w-5" />
          Emergency Stop
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-loss">
            <AlertTriangle className="h-5 w-5" />
            Emergency Stop Confirmation
          </DialogTitle>
          <DialogDescription>
            This will immediately stop the bot and cancel all pending orders. Existing positions
            will NOT be closed automatically.
          </DialogDescription>
        </DialogHeader>
        <div className="rounded-lg bg-loss/10 border border-loss/20 p-4 my-4">
          <ul className="text-sm text-loss space-y-2">
            <li className="flex items-center gap-2">
              <XCircle className="h-4 w-4" />
              Stop all bot operations immediately
            </li>
            <li className="flex items-center gap-2">
              <XCircle className="h-4 w-4" />
              Cancel all pending/open orders
            </li>
            <li className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4" />
              Existing positions will remain open
            </li>
          </ul>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setIsOpen(false)}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={handleConfirm} loading={isLoading}>
            Confirm Emergency Stop
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Bot Controls Panel
 * 
 * Main control interface for the trading bot.
 * 
 * @param {BotControlsProps} props - Component props
 * @returns {JSX.Element} Bot controls panel
 */
export function BotControls({
  status,
  onStart,
  onPause,
  onStop,
  onEmergencyStop,
  onRestart,
  isLoading = false,
}: BotControlsProps): JSX.Element {
  const isRunning = status.status === 'running'
  const isPaused = status.status === 'paused'
  const isStopped = status.status === 'stopped'
  const isTransitioning = status.status === 'starting' || status.status === 'stopping'

  return (
    <div className="space-y-6">
      {/* Main Status Card */}
      <Card className="border-2 border-border/50">
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-2xl">Bot Status</CardTitle>
              <CardDescription>Monitor and control trading bot operations</CardDescription>
            </div>
            <StatusBadge status={status.status} />
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Connection Status */}
          <div className="flex items-center gap-4">
            <div
              className={cn(
                'flex items-center gap-2 px-3 py-1.5 rounded-full text-sm',
                status.isConnected ? 'bg-profit/10 text-profit' : 'bg-loss/10 text-loss'
              )}
            >
              {status.isConnected ? (
                <Wifi className="h-4 w-4" />
              ) : (
                <WifiOff className="h-4 w-4" />
              )}
              <span>{status.isConnected ? 'API Connected' : 'API Disconnected'}</span>
            </div>
            <div
              className={cn(
                'flex items-center gap-2 px-3 py-1.5 rounded-full text-sm',
                status.signalrConnected ? 'bg-profit/10 text-profit' : 'bg-loss/10 text-loss'
              )}
            >
              <Activity className="h-4 w-4" />
              <span>{status.signalrConnected ? 'SignalR Live' : 'SignalR Offline'}</span>
            </div>
          </div>

          {/* Metrics Grid */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <MetricCard label="Uptime" value={status.uptime} icon={<Clock className="h-4 w-4" />} />
            <MetricCard
              label="Last Signal"
              value={status.lastSignal}
              icon={<Zap className="h-4 w-4" />}
            />
            <MetricCard
              label="Positions"
              value={status.activePositions}
              icon={<Activity className="h-4 w-4" />}
            />
            <MetricCard
              label="Pending"
              value={status.pendingOrders}
              icon={<Clock className="h-4 w-4" />}
            />
            <MetricCard
              label="Today's Trades"
              value={status.todayTrades}
              icon={<Activity className="h-4 w-4" />}
            />
            <MetricCard
              label="Today's P&L"
              value={`$${status.todayPnL.toLocaleString()}`}
              icon={<Activity className="h-4 w-4" />}
              trend={status.todayPnL >= 0 ? 'up' : 'down'}
            />
          </div>

          {/* Error Message */}
          {status.errorMessage && (
            <div className="flex items-start gap-3 rounded-lg bg-loss/10 border border-loss/20 p-4">
              <AlertTriangle className="h-5 w-5 text-loss shrink-0 mt-0.5" />
              <div>
                <p className="font-medium text-loss">Error Detected</p>
                <p className="text-sm text-loss/80">{status.errorMessage}</p>
              </div>
            </div>
          )}

          <Separator />

          {/* Control Buttons */}
          <div className="flex flex-wrap gap-4">
            {/* Start/Resume Button */}
            {(isStopped || isPaused) && (
              <Button
                variant="success"
                size="lg"
                className="h-14 gap-2 min-w-[140px] shadow-lg"
                onClick={onStart}
                disabled={isLoading || isTransitioning}
              >
                <Play className="h-5 w-5" />
                {isPaused ? 'Resume' : 'Start'}
              </Button>
            )}

            {/* Pause Button */}
            {isRunning && (
              <Button
                variant="outline"
                size="lg"
                className="h-14 gap-2 min-w-[140px] border-warning text-warning hover:bg-warning hover:text-warning-foreground"
                onClick={onPause}
                disabled={isLoading || isTransitioning}
              >
                <Pause className="h-5 w-5" />
                Pause
              </Button>
            )}

            {/* Stop Button */}
            {(isRunning || isPaused) && (
              <Button
                variant="outline"
                size="lg"
                className="h-14 gap-2 min-w-[140px]"
                onClick={onStop}
                disabled={isLoading || isTransitioning}
              >
                <Square className="h-5 w-5" />
                Stop
              </Button>
            )}

            {/* Restart Button */}
            {(isRunning || isPaused) && (
              <Button
                variant="outline"
                size="lg"
                className="h-14 gap-2 min-w-[140px]"
                onClick={onRestart}
                disabled={isLoading || isTransitioning}
              >
                <RefreshCw className="h-5 w-5" />
                Restart
              </Button>
            )}

            <div className="flex-1" />

            {/* Emergency Stop */}
            <EmergencyStopDialog onConfirm={onEmergencyStop} isLoading={isLoading} />
          </div>
        </CardContent>
      </Card>

      {/* Quick Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Quick Settings</CardTitle>
          <CardDescription>Toggle bot behaviors without restarting</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label className="text-base">Auto-DCA</Label>
              <p className="text-sm text-muted-foreground">
                Automatically add to losing positions
              </p>
            </div>
            <Switch defaultChecked />
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label className="text-base">Signal Processing</Label>
              <p className="text-sm text-muted-foreground">Process incoming TradingView signals</p>
            </div>
            <Switch defaultChecked />
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label className="text-base">Risk Envelope</Label>
              <p className="text-sm text-muted-foreground">Enforce position size limits</p>
            </div>
            <Switch defaultChecked />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export default BotControls
