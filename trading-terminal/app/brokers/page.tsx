/**
 * Brokers Page
 * 
 * Manage broker and exchange connections for multi-asset trading.
 * Similar to Bitsgap's "My Exchanges" feature.
 * 
 * @module app/brokers/page
 */

'use client'

import React, { useState } from 'react'
import { AppShell } from '@/components/layout'
import { ProtectedRoute } from '@/components/auth'
import { PageErrorBoundary, SectionErrorBoundary } from '@/components/error-boundary'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  Badge,
  Button,
  Input,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Label,
  Switch,
  Separator,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  useToast,
} from '@/components/ui'
import {
  Plus,
  RefreshCw,
  Settings,
  Trash2,
  CheckCircle,
  XCircle,
  AlertCircle,
  Clock,
  Wifi,
  WifiOff,
  DollarSign,
  BarChart3,
  Shield,
  ExternalLink,
  Key,
  Eye,
  EyeOff,
  Copy,
  AlertTriangle,
  Activity,
} from 'lucide-react'
import { formatCurrency, formatRelativeTime, cn } from '@/lib/utils'
import { BrokerConnection, AssetClass, ASSET_CLASS_CONFIG } from '@/lib/types/asset'
import { useBrokers, BrokersData } from '@/lib/hooks'
import { getAuthHeaders } from '@/lib/admin-api'

// Mock broker connections data (fallback when API unavailable)
const mockBrokers: BrokerConnection[] = [
  {
    id: 'alpaca-1',
    name: 'Alpaca',
    type: 'broker',
    status: 'connected',
    supportedAssets: ['stock', 'etf', 'crypto'],
    balance: 125000,
    buyingPower: 45000,
    portfolioValue: 68432.50,
    openPositions: 5,
    lastSync: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
    apiKeyMasked: '****-****-****-1234',
    isPaper: false,
    logoUrl: '/brokers/alpaca.svg',
  },
  {
    id: 'alpaca-paper',
    name: 'Alpaca (Paper)',
    type: 'broker',
    status: 'connected',
    supportedAssets: ['stock', 'etf', 'crypto'],
    balance: 100000,
    buyingPower: 100000,
    portfolioValue: 0,
    openPositions: 0,
    lastSync: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    apiKeyMasked: '****-****-****-5678',
    isPaper: true,
    logoUrl: '/brokers/alpaca.svg',
  },
  {
    id: 'tastytrade-1',
    name: 'Tastytrade',
    type: 'broker',
    status: 'connected',
    supportedAssets: ['stock', 'etf'],
    balance: 75000,
    buyingPower: 32500,
    portfolioValue: 42500,
    openPositions: 3,
    lastSync: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
    apiKeyMasked: '****-****-****-9012',
    isPaper: false,
    logoUrl: '/brokers/tastytrade.svg',
  },
  {
    id: 'oanda-1',
    name: 'OANDA',
    type: 'broker',
    status: 'error',
    supportedAssets: ['forex'],
    balance: 0,
    buyingPower: 0,
    portfolioValue: 0,
    openPositions: 0,
    lastSync: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
    apiKeyMasked: '****-****-****-3456',
    isPaper: false,
    logoUrl: '/brokers/oanda.svg',
  },
]

// Available brokers to add
const availableBrokers = [
  { id: 'alpaca', name: 'Alpaca', assets: ['stock', 'etf', 'crypto'], hasPaper: true },
  { id: 'tastytrade', name: 'Tastytrade', assets: ['stock', 'etf'], hasPaper: false },
  { id: 'oanda', name: 'OANDA', assets: ['forex'], hasPaper: true },
  { id: 'interactive-brokers', name: 'Interactive Brokers', assets: ['stock', 'etf', 'forex', 'commodity'], hasPaper: true },
  { id: 'tradier', name: 'Tradier', assets: ['stock', 'etf'], hasPaper: true },
  { id: 'coinbase', name: 'Coinbase', assets: ['crypto'], hasPaper: false },
  { id: 'kraken', name: 'Kraken', assets: ['crypto'], hasPaper: false },
]

/**
 * Status badge component
 */
function StatusBadge({ status }: { status: BrokerConnection['status'] }) {
  const config = {
    connected: { icon: CheckCircle, label: 'Connected', variant: 'success' as const },
    disconnected: { icon: WifiOff, label: 'Disconnected', variant: 'secondary' as const },
    error: { icon: XCircle, label: 'Error', variant: 'destructive' as const },
    pending: { icon: Clock, label: 'Pending', variant: 'outline' as const },
  }
  
  const { icon: Icon, label, variant } = config[status]
  
  return (
    <Badge variant={variant} className="gap-1">
      <Icon className="h-3 w-3" />
      {label}
    </Badge>
  )
}

/**
 * Add Broker Dialog
 */
function AddBrokerDialog({ onBrokerAdded }: { onBrokerAdded?: () => void }) {
  const [isOpen, setIsOpen] = useState(false)
  const [selectedBroker, setSelectedBroker] = useState<string>('')
  const [isPaper, setIsPaper] = useState(false)
  const [showApiKey, setShowApiKey] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [isConnecting, setIsConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const broker = availableBrokers.find(b => b.id === selectedBroker)

  const handleConnect = async () => {
    if (!selectedBroker || !apiKey || !apiSecret) return
    
    setIsConnecting(true)
    setError(null)
    
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'
      const headers = await getAuthHeaders()
      const response = await fetch(`${API_URL}/api/v1/admin/brokers`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          broker_type: selectedBroker,
          name: broker?.name + (isPaper ? ' (Paper)' : ''),
          credentials: {
            api_key: apiKey,
            api_secret: apiSecret,
            is_paper: isPaper,
          },
        }),
      })
      
      const data = await response.json()
      
      if (data.success) {
        // Success - close dialog and refresh list
        setIsOpen(false)
        setSelectedBroker('')
        setApiKey('')
        setApiSecret('')
        setIsPaper(false)
        onBrokerAdded?.()
      } else {
        setError(data.message || 'Failed to connect broker')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Connection failed')
    } finally {
      setIsConnecting(false)
    }
  }

  const resetForm = () => {
    setSelectedBroker('')
    setApiKey('')
    setApiSecret('')
    setIsPaper(false)
    setError(null)
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { setIsOpen(open); if (!open) resetForm(); }}>
      <DialogTrigger asChild>
        <Button className="gap-2">
          <Plus className="h-4 w-4" />
          Add Broker
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Connect a Broker</DialogTitle>
          <DialogDescription>
            Add API credentials to connect your brokerage account
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4 py-4">
          {/* Broker Selection */}
          <div className="space-y-2">
            <Label>Select Broker</Label>
            <Select value={selectedBroker} onValueChange={setSelectedBroker}>
              <SelectTrigger>
                <SelectValue placeholder="Choose a broker..." />
              </SelectTrigger>
              <SelectContent>
                {availableBrokers.map((b) => (
                  <SelectItem key={b.id} value={b.id}>
                    <div className="flex items-center gap-2">
                      <span>{b.name}</span>
                      <div className="flex gap-1">
                        {b.assets.map((asset) => (
                          <span key={asset} className="text-xs text-muted-foreground">
                            {ASSET_CLASS_CONFIG[asset as AssetClass].icon}
                          </span>
                        ))}
                      </div>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {selectedBroker && (
            <>
              {/* Supported Assets */}
              <div className="p-3 rounded-lg bg-muted/50">
                <p className="text-sm text-muted-foreground mb-2">Supported Assets</p>
                <div className="flex flex-wrap gap-2">
                  {broker?.assets.map((asset) => {
                    const config = ASSET_CLASS_CONFIG[asset as AssetClass]
                    return (
                      <Badge key={asset} variant="secondary" className={cn('gap-1', config.color)}>
                        <span>{config.icon}</span>
                        {config.label}
                      </Badge>
                    )
                  })}
                </div>
              </div>

              {/* Paper Trading Toggle */}
              {broker?.hasPaper && (
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Paper Trading</Label>
                    <p className="text-sm text-muted-foreground">
                      Use sandbox/demo account
                    </p>
                  </div>
                  <Switch checked={isPaper} onCheckedChange={setIsPaper} />
                </div>
              )}

              <Separator />

              {/* API Credentials */}
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="apiKey">API Key</Label>
                  <div className="relative">
                    <Input
                      id="apiKey"
                      type={showApiKey ? 'text' : 'password'}
                      placeholder="Enter your API key"
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7 p-0"
                      onClick={() => setShowApiKey(!showApiKey)}
                    >
                      {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </Button>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="apiSecret">API Secret</Label>
                  <Input
                    id="apiSecret"
                    type="password"
                    placeholder="Enter your API secret"
                    value={apiSecret}
                    onChange={(e) => setApiSecret(e.target.value)}
                  />
                </div>
              </div>

              {/* Security Note */}
              <div className="flex items-start gap-3 p-3 rounded-lg bg-blue-500/10 border border-blue-500/20">
                <Shield className="h-5 w-5 text-blue-500 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-blue-500">Session-Only Storage</p>
                  <p className="text-xs text-muted-foreground">
                    Credentials are stored in memory for this session only. On restart, re-enter credentials or configure via environment variables.
                  </p>
                </div>
              </div>

              {/* Error Display */}
              {error && (
                <div className="flex items-start gap-3 p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                  <AlertTriangle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-red-500">Connection Failed</p>
                    <p className="text-xs text-muted-foreground">{error}</p>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setIsOpen(false)} disabled={isConnecting}>
            Cancel
          </Button>
          <Button 
            disabled={!selectedBroker || !apiKey || !apiSecret || isConnecting}
            onClick={handleConnect}
          >
            {isConnecting ? (
              <>
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                Connecting...
              </>
            ) : (
              'Connect Broker'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Broker Settings Dialog Component
 */
function BrokerSettingsDialog({ 
  broker, 
  open, 
  onOpenChange,
  onUpdated 
}: { 
  broker: BrokerConnection
  open: boolean
  onOpenChange: (open: boolean) => void
  onUpdated?: () => void
}) {
  const [displayName, setDisplayName] = useState(broker.name)
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [showApiKey, setShowApiKey] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const { toast } = useToast()

  const hasChanges = displayName !== broker.name || apiKey.length > 0 || apiSecret.length > 0

  const handleSave = async () => {
    if (!hasChanges) return
    
    setIsSaving(true)
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'
      const headers = await getAuthHeaders()
      
      // Build update payload - only include changed fields
      const updatePayload: Record<string, unknown> = {}
      if (displayName !== broker.name) {
        updatePayload.name = displayName
      }
      if (apiKey && apiSecret) {
        updatePayload.credentials = {
          api_key: apiKey,
          api_secret: apiSecret,
        }
      }
      
      const response = await fetch(`${API_URL}/api/v1/admin/brokers/${broker.id}`, {
        method: 'PATCH',
        headers,
        body: JSON.stringify(updatePayload),
      })
      
      const data = await response.json().catch(() => null)
      
      // Check both HTTP status and explicit success flag from response
      if (response.ok && data?.success === true) {
        toast({
          title: 'Settings Updated',
          description: data?.message || `Successfully updated ${displayName}`,
        })
        onOpenChange(false)
        onUpdated?.()
        // Reset credential fields
        setApiKey('')
        setApiSecret('')
      } else {
        toast({
          title: 'Update Failed',
          description: data?.message || data?.detail || 'Failed to update broker settings',
          variant: 'destructive',
        })
      }
    } catch (err) {
      toast({
        title: 'Connection Error',
        description: err instanceof Error ? err.message : 'Failed to connect to server',
        variant: 'destructive',
      })
    } finally {
      setIsSaving(false)
    }
  }

  // Reset form when dialog opens
  React.useEffect(() => {
    if (open) {
      setDisplayName(broker.name)
      setApiKey('')
      setApiSecret('')
      setShowApiKey(false)
    }
  }, [open, broker.name])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Broker Settings</DialogTitle>
          <DialogDescription>
            Update connection settings for {broker.name}
          </DialogDescription>
        </DialogHeader>
        
        <div className="grid gap-4 py-4">
          {/* Display Name */}
          <div className="grid gap-2">
            <Label htmlFor="displayName">Display Name</Label>
            <Input
              id="displayName"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="e.g., My Trading Account"
            />
          </div>
          
          <Separator />
          
          {/* API Credentials Section */}
          <div className="space-y-2">
            <Label className="text-sm font-medium">Update API Credentials</Label>
            <p className="text-xs text-muted-foreground">
              Leave blank to keep existing credentials. Both fields required to update.
            </p>
          </div>
          
          <div className="grid gap-2">
            <Label htmlFor="apiKey">API Key</Label>
            <div className="relative">
              <Input
                id="apiKey"
                type={showApiKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={broker.apiKeyMasked || 'Enter new API key'}
                className="pr-10"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3"
                onClick={() => setShowApiKey(!showApiKey)}
              >
                {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
            </div>
          </div>
          
          <div className="grid gap-2">
            <Label htmlFor="apiSecret">API Secret</Label>
            <Input
              id="apiSecret"
              type="password"
              value={apiSecret}
              onChange={(e) => setApiSecret(e.target.value)}
              placeholder="Enter new API secret"
            />
          </div>
          
          {/* Validation message */}
          {(apiKey && !apiSecret) || (!apiKey && apiSecret) ? (
            <p className="text-xs text-amber-500">
              Both API Key and Secret are required to update credentials
            </p>
          ) : null}
          
          {/* Current Connection Info */}
          <Separator />
          <div className="rounded-lg bg-muted/50 p-3 space-y-2">
            <p className="text-xs font-medium text-muted-foreground">Connection Info</p>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <span className="text-muted-foreground">Broker:</span>
              <span className="font-medium capitalize">{broker.brokerType || broker.type}</span>
              <span className="text-muted-foreground">Mode:</span>
              <span className="font-medium">{broker.isPaper ? 'Paper Trading' : 'Live Trading'}</span>
              <span className="text-muted-foreground">Status:</span>
              <span className={cn(
                'font-medium',
                broker.status === 'connected' && 'text-green-500',
                broker.status === 'error' && 'text-red-500'
              )}>
                {broker.status}
              </span>
            </div>
          </div>
        </div>
        
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSaving}>
            Cancel
          </Button>
          <Button 
            onClick={handleSave} 
            disabled={isSaving || !hasChanges || (Boolean(apiKey || apiSecret) && !(apiKey && apiSecret))}
          >
            {isSaving ? (
              <>
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              'Save Changes'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Broker Card Component
 */
function BrokerCard({ broker, onDeleted, onRefresh }: { broker: BrokerConnection; onDeleted?: () => void; onRefresh?: () => void }) {
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const { toast } = useToast()

  const handleRefresh = async () => {
    setIsRefreshing(true)
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'
      const headers = await getAuthHeaders()
      
      const response = await fetch(`${API_URL}/api/v1/admin/brokers/refresh`, {
        method: 'POST',
        headers,
      })
      
      if (response.ok) {
        toast({
          title: 'Connections Refreshed',
          description: 'Successfully refreshed all broker connections',
        })
        onRefresh?.()
      } else {
        const data = await response.json().catch(() => null)
        toast({
          title: 'Refresh Failed',
          description: data?.message || data?.detail || 'Failed to refresh broker connections',
          variant: 'destructive',
        })
      }
    } catch (err) {
      toast({
        title: 'Connection Error',
        description: err instanceof Error ? err.message : 'Failed to connect to server',
        variant: 'destructive',
      })
    } finally {
      setIsRefreshing(false)
    }
  }

  const handleDelete = async () => {
    setIsDeleting(true)
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'
      const deleteUrl = `${API_URL}/api/v1/admin/brokers/${broker.id}`
      const headers = await getAuthHeaders()
      
      const response = await fetch(deleteUrl, {
        method: 'DELETE',
        headers,
      })
      
      const responseData = await response.json().catch(() => null)
      
      if (response.ok) {
        setShowDeleteConfirm(false)
        toast({
          title: 'Broker Disconnected',
          description: `Successfully disconnected ${broker.name}`,
        })
        onDeleted?.()
      } else {
        const errorMessage = responseData?.detail || responseData?.message || 'Unknown error'
        toast({
          title: 'Disconnect Failed',
          description: errorMessage,
          variant: 'destructive',
        })
      }
    } catch (err) {
      toast({
        title: 'Connection Error',
        description: err instanceof Error ? err.message : 'Failed to connect to server',
        variant: 'destructive',
      })
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <Card className={cn(
      'relative overflow-hidden transition-all',
      broker.status === 'error' && 'border-red-500/50',
      broker.status === 'connected' && 'hover:border-primary/50'
    )}>
      {/* Paper badge */}
      {broker.isPaper && (
        <div className="absolute top-0 right-0 px-3 py-1 bg-amber-500 text-amber-950 text-xs font-medium rounded-bl-lg">
          PAPER
        </div>
      )}

      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            {/* Broker Logo Placeholder */}
            <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-primary/20 to-primary/5 flex items-center justify-center">
              <span className="text-lg font-bold">{broker.name[0]}</span>
            </div>
            <div>
              <CardTitle className="text-lg">{broker.name}</CardTitle>
              <div className="flex items-center gap-2 mt-1">
                <StatusBadge status={broker.status} />
                <Badge variant="outline" className="text-xs capitalize">
                  {broker.brokerType || broker.type}
                </Badge>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRefresh}
              disabled={isRefreshing}
              title="Refresh account data"
            >
              <RefreshCw className={cn('h-4 w-4', isRefreshing && 'animate-spin')} />
            </Button>
            <Button 
              variant="ghost" 
              size="sm"
              onClick={() => setShowSettings(true)}
              title="Connection settings"
            >
              <Settings className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      
      {/* Settings Dialog */}
      <BrokerSettingsDialog
        broker={broker}
        open={showSettings}
        onOpenChange={setShowSettings}
        onUpdated={onRefresh}
      />

      <CardContent className="space-y-4">
        {/* Supported Assets */}
        <div className="flex flex-wrap gap-1">
          {(broker.supportedAssets || []).map((asset) => {
            const config = ASSET_CLASS_CONFIG[asset]
            if (!config) return null
            return (
              <Badge key={asset} variant="secondary" className={cn('text-xs gap-1', config.color)}>
                <span>{config.icon}</span>
                {config.label}
              </Badge>
            )
          })}
        </div>

        {/* Error Message */}
        {broker.status === 'error' && (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20">
            <AlertTriangle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm text-red-500 font-medium">Connection Error</p>
              <p className="text-xs text-muted-foreground">
                Unable to connect. Please check your API credentials.
              </p>
            </div>
          </div>
        )}

        {/* Account Stats */}
        {broker.status === 'connected' && (
          <div className="grid grid-cols-2 gap-4">
            <div className="p-3 rounded-lg bg-muted/50">
              <div className="flex items-center gap-2 text-muted-foreground mb-1">
                <DollarSign className="h-4 w-4" />
                <span className="text-xs">Portfolio Value</span>
              </div>
              <p className="text-lg font-bold">{formatCurrency(broker.portfolioValue)}</p>
            </div>
            <div className="p-3 rounded-lg bg-muted/50">
              <div className="flex items-center gap-2 text-muted-foreground mb-1">
                <BarChart3 className="h-4 w-4" />
                <span className="text-xs">Buying Power</span>
              </div>
              <p className="text-lg font-bold">{formatCurrency(broker.buyingPower)}</p>
            </div>
            <div className="p-3 rounded-lg bg-muted/50">
              <div className="flex items-center gap-2 text-muted-foreground mb-1">
                <Activity className="h-4 w-4" />
                <span className="text-xs">Open Positions</span>
              </div>
              <p className="text-lg font-bold">{broker.openPositions}</p>
            </div>
            <div className="p-3 rounded-lg bg-muted/50">
              <div className="flex items-center gap-2 text-muted-foreground mb-1">
                <Clock className="h-4 w-4" />
                <span className="text-xs">Last Sync</span>
              </div>
              <p className="text-sm font-medium">{formatRelativeTime(broker.lastSync)}</p>
            </div>
          </div>
        )}

        {/* API Key Info */}
        <div className="flex items-center justify-between pt-2 border-t">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Key className="h-4 w-4" />
            <span className="font-mono">{broker.apiKeyMasked}</span>
            <Button variant="ghost" size="sm" className="h-6 w-6 p-0">
              <Copy className="h-3 w-3" />
            </Button>
          </div>
          <Dialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
            <DialogTrigger asChild>
              <Button variant="ghost" size="sm" className="text-red-500 hover:text-red-600 hover:bg-red-500/10">
                <Trash2 className="h-4 w-4" />
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Disconnect Broker</DialogTitle>
                <DialogDescription>
                  Are you sure you want to disconnect {broker.name}? This will remove the connection from your account.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={() => setShowDeleteConfirm(false)} disabled={isDeleting}>
                  Cancel
                </Button>
                <Button variant="destructive" onClick={handleDelete} disabled={isDeleting}>
                  {isDeleting ? (
                    <>
                      <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                      Disconnecting...
                    </>
                  ) : (
                    <>
                      <Trash2 className="h-4 w-4 mr-2" />
                      Disconnect
                    </>
                  )}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Summary Stats
 */
function BrokersSummary({ brokers }: { brokers: BrokerConnection[] }) {
  const connectedBrokers = brokers.filter(b => b.status === 'connected')
  const totalPortfolioValue = connectedBrokers.reduce((sum, b) => sum + (b.portfolioValue || 0), 0)
  const totalBuyingPower = connectedBrokers.reduce((sum, b) => sum + (b.buyingPower || 0), 0)
  const totalPositions = connectedBrokers.reduce((sum, b) => sum + (b.openPositions || 0), 0)

  // Collect all unique supported assets
  const allAssets = new Set<AssetClass>()
  connectedBrokers.forEach(b => (b.supportedAssets || []).forEach(a => allAssets.add(a)))

  return (
    <div className="grid gap-4 md:grid-cols-4">
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Connected Brokers</p>
              <p className="text-2xl font-bold">{connectedBrokers.length}</p>
              <p className="text-xs text-muted-foreground">of {brokers.length} total</p>
            </div>
            <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
              <Wifi className="h-5 w-5 text-primary" />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Total Portfolio</p>
              <p className="text-2xl font-bold">{formatCurrency(totalPortfolioValue)}</p>
              <p className="text-xs text-muted-foreground">Across all brokers</p>
            </div>
            <div className="h-10 w-10 rounded-full bg-emerald-500/10 flex items-center justify-center">
              <DollarSign className="h-5 w-5 text-emerald-500" />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Total Buying Power</p>
              <p className="text-2xl font-bold">{formatCurrency(totalBuyingPower)}</p>
              <p className="text-xs text-muted-foreground">Available to trade</p>
            </div>
            <div className="h-10 w-10 rounded-full bg-blue-500/10 flex items-center justify-center">
              <BarChart3 className="h-5 w-5 text-blue-500" />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Asset Classes</p>
              <div className="flex gap-1 mt-1">
                {Array.from(allAssets).map(asset => (
                  <span key={asset} className="text-lg">
                    {ASSET_CLASS_CONFIG[asset].icon}
                  </span>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">{allAssets.size} available</p>
            </div>
            <div className="h-10 w-10 rounded-full bg-purple-500/10 flex items-center justify-center">
              <Activity className="h-5 w-5 text-purple-500" />
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * Skeleton loader for broker cards
 */
function BrokerCardSkeleton() {
  return (
    <Card className="relative overflow-hidden">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <Skeleton className="w-12 h-12 rounded-lg" />
            <div>
              <Skeleton className="h-5 w-24 mb-2" />
              <div className="flex items-center gap-2">
                <Skeleton className="h-5 w-20" />
                <Skeleton className="h-5 w-16" />
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <Skeleton className="h-8 w-8" />
            <Skeleton className="h-8 w-8" />
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-1">
          <Skeleton className="h-5 w-16" />
          <Skeleton className="h-5 w-14" />
          <Skeleton className="h-5 w-18" />
        </div>
        <div className="grid grid-cols-2 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="p-3 rounded-lg bg-muted/50">
              <Skeleton className="h-3 w-20 mb-2" />
              <Skeleton className="h-6 w-24" />
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between pt-2 border-t">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-8 w-8" />
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Skeleton loader for summary stats
 */
function BrokersSummarySkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-4">
      {[...Array(4)].map((_, i) => (
        <Card key={i}>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <Skeleton className="h-4 w-24 mb-2" />
                <Skeleton className="h-8 w-16 mb-1" />
                <Skeleton className="h-3 w-20" />
              </div>
              <Skeleton className="h-10 w-10 rounded-full" />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

/**
 * Error state component
 */
function BrokersError({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <Card className="py-12 border-red-500/50">
      <CardContent className="text-center">
        <div className="h-16 w-16 rounded-full bg-red-500/10 mx-auto flex items-center justify-center mb-4">
          <AlertCircle className="h-8 w-8 text-red-500" />
        </div>
        <h3 className="text-lg font-semibold mb-2">Failed to Load Brokers</h3>
        <p className="text-muted-foreground mb-4 max-w-md mx-auto">
          {error}
        </p>
        <Button onClick={onRetry} variant="outline" className="gap-2">
          <RefreshCw className="h-4 w-4" />
          Try Again
        </Button>
      </CardContent>
    </Card>
  )
}

/**
 * Brokers Page Component
 * 
 * Displays broker connections with loading, error, and empty states.
 * Uses useBrokers hook for data fetching. Demo mode requires explicit user opt-in
 * to prevent masking real API failures.
 */
export default function BrokersPage() {
  const [useDemoMode, setUseDemoMode] = useState(false)
  const { data, isLoading, error, refetch } = useBrokers()
  
  // Separate "API reachable" from "has brokers" to avoid misleading empty-state
  const isApiAvailable = data !== null && !error
  const hasBrokers = isApiAvailable && data.connections && data.connections.length > 0
  const brokers = hasBrokers ? data.connections : (useDemoMode ? mockBrokers : [])
  
  // Show empty state only when API failed to respond (not when list is legitimately empty)
  const showApiFailedState = !isLoading && !isApiAvailable && !useDemoMode
  // Show "no brokers configured" when API works but returns empty list
  const showNoBrokersState = !isLoading && isApiAvailable && !hasBrokers && !useDemoMode

  // Exit demo mode when real brokers become available
  React.useEffect(() => {
    if (hasBrokers && useDemoMode) {
      setUseDemoMode(false)
    }
  }, [hasBrokers, useDemoMode])

  return (
    <ProtectedRoute>
      <PageErrorBoundary pageName="Brokers">
        <AppShell>
          <div className="space-y-6">
            {/* Demo Mode Active Warning */}
            {useDemoMode && !isLoading && (
              <Card className="border-amber-500/50 bg-amber-500/5">
                <CardContent className="flex items-center gap-4 py-4">
                  <div className="h-10 w-10 rounded-full bg-amber-500/10 flex items-center justify-center flex-shrink-0">
                    <AlertTriangle className="h-5 w-5 text-amber-500" />
                  </div>
                  <div className="flex-1">
                    <h4 className="font-medium text-amber-700 dark:text-amber-400">Demo Mode Active</h4>
                    <p className="text-sm text-muted-foreground">
                      Showing sample broker data. This is not your real broker configuration.
                    </p>
                  </div>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    onClick={() => {
                      setUseDemoMode(false)
                      refetch()
                    }} 
                    className="gap-2"
                  >
                    Exit Demo Mode
                  </Button>
                </CardContent>
              </Card>
            )}

            {/* API Failed State - Connection problem, prompt demo mode */}
            {showApiFailedState && (
              <Card className="border-muted">
                <CardContent className="py-12">
                  <div className="flex flex-col items-center justify-center text-center space-y-4">
                    <div className="h-16 w-16 rounded-full bg-muted flex items-center justify-center">
                      <Wifi className="h-8 w-8 text-muted-foreground" />
                    </div>
                    <div className="space-y-2">
                      <h3 className="text-lg font-semibold">Connection Failed</h3>
                      <p className="text-sm text-muted-foreground max-w-md">
                        Unable to connect to the trading API. Check your backend connection
                        or try demo mode to explore the interface.
                      </p>
                    </div>
                    <div className="flex gap-3">
                      <Button variant="outline" onClick={refetch}>
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Retry Connection
                      </Button>
                      <Button onClick={() => setUseDemoMode(true)}>
                        <Activity className="h-4 w-4 mr-2" />
                        Use Demo Data
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* No Brokers State - API works but no brokers configured */}
            {showNoBrokersState && (
              <Card className="border-dashed border-2">
                <CardContent className="py-12">
                  <div className="flex flex-col items-center justify-center text-center space-y-4">
                    <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
                      <Plus className="h-8 w-8 text-primary" />
                    </div>
                    <div className="space-y-2">
                      <h3 className="text-lg font-semibold">No Brokers Configured</h3>
                      <p className="text-sm text-muted-foreground max-w-md">
                        Get started by adding your first broker connection.
                        You can connect to Alpaca, TastyTrade, or other supported brokers.
                      </p>
                    </div>
                    <AddBrokerDialog onBrokerAdded={refetch} />
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Page Header */}
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-3xl font-bold tracking-tight">Brokers</h1>
                <p className="text-muted-foreground">
                  Manage your broker and exchange connections
                </p>
              </div>
              <div className="flex items-center gap-2">
                {isApiAvailable && (
                  <Badge variant="outline" className="gap-1 text-green-500 border-green-500/50">
                    <CheckCircle className="h-3 w-3" />
                    Live
                  </Badge>
                )}
                <AddBrokerDialog onBrokerAdded={refetch} />
              </div>
            </div>

            {/* Loading State */}
          {isLoading && (
            <>
              <BrokersSummarySkeleton />
              <div className="grid gap-4 md:grid-cols-2">
                <BrokerCardSkeleton />
                <BrokerCardSkeleton />
              </div>
            </>
          )}

          {/* Error State - only show if not already showing API failed state */}
          {error && !isLoading && !showApiFailedState && (
            <BrokersError error={error.message} onRetry={refetch} />
          )}

          {/* Content (shown only when we have data - real or demo) */}
          {!isLoading && !showApiFailedState && !showNoBrokersState && brokers.length > 0 && (
            <>
              {/* Summary Stats */}
              <SectionErrorBoundary sectionName="Broker Summary">
                <BrokersSummary brokers={brokers} />
              </SectionErrorBoundary>

              {/* Broker Cards Grid */}
              <SectionErrorBoundary sectionName="Broker Connections">
                <div className="grid gap-4 md:grid-cols-2">
                  {brokers.map((broker) => (
                    <BrokerCard key={broker.id} broker={broker} onDeleted={refetch} onRefresh={refetch} />
                  ))}
                </div>
              </SectionErrorBoundary>
            </>
          )}
        </div>
        </AppShell>
      </PageErrorBoundary>
    </ProtectedRoute>
  )
}
