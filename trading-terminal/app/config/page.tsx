/**
 * Configuration Page
 * 
 * Settings management for DCA strategy, risk parameters, and trading preferences.
 * 
 * @module app/config/page
 */

'use client'

import React from 'react'
import { AppShell } from '@/components/layout'
import { ProtectedRoute } from '@/components/auth'
import { ConfigEditor } from '@/components/trading'
import { Card, CardContent, CardHeader, CardTitle, Badge } from '@/components/ui'
import { 
  Settings2, 
  History, 
  Save,
  RotateCcw,
  Clock,
  CheckCircle2,
} from 'lucide-react'

/** Configuration history entry */
interface ConfigChange {
  timestamp: string
  user: string
  changes: string
  version: string
}

/** Mock configuration history */
const configHistory: ConfigChange[] = [
  { timestamp: '2024-03-15 14:32:00', user: 'admin@example.com', changes: 'Updated DCA layers from 4 to 5', version: 'v1.5' },
  { timestamp: '2024-03-14 10:15:00', user: 'admin@example.com', changes: 'Increased max position size to 12%', version: 'v1.4' },
  { timestamp: '2024-03-12 09:00:00', user: 'admin@example.com', changes: 'Enabled extended hours trading', version: 'v1.3' },
  { timestamp: '2024-03-10 16:45:00', user: 'admin@example.com', changes: 'Adjusted risk multiplier to 1.8x', version: 'v1.2' },
  { timestamp: '2024-03-08 11:20:00', user: 'admin@example.com', changes: 'Initial configuration setup', version: 'v1.0' },
]

/** Configuration presets */
const presets = [
  { name: 'Conservative', description: 'Low risk, slower gains', riskLevel: 1 },
  { name: 'Moderate', description: 'Balanced risk/reward', riskLevel: 2 },
  { name: 'Aggressive', description: 'Higher risk, faster gains', riskLevel: 3 },
  { name: 'Custom', description: 'Your current settings', riskLevel: 0 },
]

/**
 * ConfigHistory Component
 * 
 * Displays configuration change history.
 */
function ConfigHistory() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <History className="h-5 w-5" />
          Configuration History
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {configHistory.map((change, index) => (
            <div 
              key={index}
              className="flex items-start gap-3 p-3 rounded-lg bg-muted/50 hover:bg-muted transition-colors"
            >
              <div className="flex-shrink-0 mt-0.5">
                <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
                  <Save className="h-4 w-4 text-primary" />
                </div>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-xs">{change.version}</Badge>
                  <span className="text-xs text-muted-foreground">{change.timestamp}</span>
                </div>
                <p className="text-sm font-medium mt-1">{change.changes}</p>
                <p className="text-xs text-muted-foreground mt-0.5">by {change.user}</p>
              </div>
              <button className="flex-shrink-0 p-2 rounded-md hover:bg-background transition-colors">
                <RotateCcw className="h-4 w-4 text-muted-foreground" />
              </button>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * PresetSelector Component
 * 
 * Quick preset selection for common configurations.
 */
function PresetSelector({ onSelect }: { onSelect: (preset: string) => void }) {
  const [selected, setSelected] = React.useState('Custom')

  const handleSelect = (name: string) => {
    setSelected(name)
    onSelect(name)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Settings2 className="h-5 w-5" />
          Quick Presets
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-3">
          {presets.map((preset) => (
            <button
              key={preset.name}
              onClick={() => handleSelect(preset.name)}
              className={`p-4 rounded-lg border-2 text-left transition-all ${
                selected === preset.name
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/50 hover:bg-muted/50'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-medium">{preset.name}</span>
                {selected === preset.name && (
                  <CheckCircle2 className="h-4 w-4 text-primary" />
                )}
              </div>
              <p className="text-xs text-muted-foreground">{preset.description}</p>
              {preset.riskLevel > 0 && (
                <div className="flex gap-1 mt-2">
                  {[1, 2, 3].map((level) => (
                    <div
                      key={level}
                      className={`h-1.5 flex-1 rounded-full ${
                        level <= preset.riskLevel
                          ? level === 1
                            ? 'bg-emerald-500'
                            : level === 2
                            ? 'bg-yellow-500'
                            : 'bg-red-500'
                          : 'bg-muted'
                      }`}
                    />
                  ))}
                </div>
              )}
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * LastSaved Component
 * 
 * Shows when configuration was last saved.
 */
function LastSaved() {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-full bg-emerald-500/10 flex items-center justify-center">
            <CheckCircle2 className="h-5 w-5 text-emerald-500" />
          </div>
          <div>
            <p className="text-sm font-medium">Configuration Synced</p>
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" />
              Last saved 5 minutes ago
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Configuration Page Component
 */
export default function ConfigPage() {
  const handlePresetSelect = (preset: string) => {
    console.log('Selected preset:', preset)
    // TODO: Load preset configuration
  }

  return (
    <ProtectedRoute>
      <AppShell>
        <div className="space-y-6">
          {/* Page Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">Configuration</h1>
              <p className="text-muted-foreground">
                Manage your trading bot settings and parameters
              </p>
            </div>
            <Badge variant="outline" className="gap-1">
              <Settings2 className="h-3 w-3" />
              v1.5
            </Badge>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            {/* Main Config Editor */}
            <div className="lg:col-span-2 space-y-6">
              <ConfigEditor />
            </div>

            {/* Sidebar */}
            <div className="space-y-6">
              <LastSaved />
              <PresetSelector onSelect={handlePresetSelect} />
              <ConfigHistory />
            </div>
          </div>
        </div>
      </AppShell>
    </ProtectedRoute>
  )
}
