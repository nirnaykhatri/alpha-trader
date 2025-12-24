/**
 * Order History Page
 * 
 * Displays complete order history with filtering and search.
 * 
 * @module app/orders/page
 */

'use client'

import React from 'react'
import { AppShell } from '@/components/layout'
import { ProtectedRoute } from '@/components/auth'
import { OrderHistory } from '@/components/tables'
import { Card, CardContent, CardHeader, CardTitle, Badge } from '@/components/ui'
import { 
  BarChart3, 
  TrendingUp, 
  Clock, 
  CheckCircle2,
  XCircle,
  AlertCircle,
} from 'lucide-react'
import { formatCurrency } from '@/lib/utils'

/** Order statistics */
interface OrderStats {
  totalOrders: number
  filledOrders: number
  cancelledOrders: number
  pendingOrders: number
  totalVolume: number
  avgFillRate: number
}

/** Mock order statistics */
const mockStats: OrderStats = {
  totalOrders: 1247,
  filledOrders: 1189,
  cancelledOrders: 42,
  pendingOrders: 16,
  totalVolume: 2345678.90,
  avgFillRate: 95.35,
}

/**
 * StatCard Component
 * 
 * Displays a single statistic with icon and value.
 */
function StatCard({
  title,
  value,
  icon: Icon,
  variant = 'default',
}: {
  title: string
  value: string | number
  icon: React.ElementType
  variant?: 'default' | 'success' | 'danger' | 'warning'
}) {
  const variantStyles = {
    default: 'text-muted-foreground',
    success: 'text-emerald-500',
    danger: 'text-red-500',
    warning: 'text-yellow-500',
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        <Icon className={`h-4 w-4 ${variantStyles[variant]}`} />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
      </CardContent>
    </Card>
  )
}

/**
 * Order History Page Component
 * 
 * Main page for viewing and managing order history.
 */
export default function OrdersPage() {
  return (
    <ProtectedRoute>
      <AppShell>
        <div className="space-y-6">
          {/* Page Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">Order History</h1>
              <p className="text-muted-foreground">
                View and manage all your trading orders
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="gap-1">
                <Clock className="h-3 w-3" />
                Last updated: Just now
              </Badge>
            </div>
          </div>

          {/* Statistics Grid */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <StatCard
              title="Total Orders"
              value={mockStats.totalOrders.toLocaleString()}
              icon={BarChart3}
            />
            <StatCard
              title="Filled Orders"
              value={mockStats.filledOrders.toLocaleString()}
              icon={CheckCircle2}
              variant="success"
            />
            <StatCard
              title="Pending Orders"
              value={mockStats.pendingOrders}
              icon={AlertCircle}
              variant="warning"
            />
            <StatCard
              title="Fill Rate"
              value={`${mockStats.avgFillRate}%`}
              icon={TrendingUp}
              variant="success"
            />
          </div>

          {/* Volume Summary */}
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">Total Volume</p>
                    <p className="text-2xl font-bold">{formatCurrency(mockStats.totalVolume)}</p>
                  </div>
                  <div className="h-12 w-12 rounded-full bg-blue-500/10 flex items-center justify-center">
                    <TrendingUp className="h-6 w-6 text-blue-500" />
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">Cancelled</p>
                    <p className="text-2xl font-bold">{mockStats.cancelledOrders}</p>
                  </div>
                  <div className="h-12 w-12 rounded-full bg-red-500/10 flex items-center justify-center">
                    <XCircle className="h-6 w-6 text-red-500" />
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">Success Rate</p>
                    <p className="text-2xl font-bold">{mockStats.avgFillRate}%</p>
                  </div>
                  <div className="h-12 w-12 rounded-full bg-emerald-500/10 flex items-center justify-center">
                    <CheckCircle2 className="h-6 w-6 text-emerald-500" />
                  </div>
                </div>
                <div className="mt-2 h-2 bg-muted rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-emerald-500 rounded-full transition-all"
                    style={{ width: `${mockStats.avgFillRate}%` }}
                  />
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Order History Table */}
          <OrderHistory />
        </div>
      </AppShell>
    </ProtectedRoute>
  )
}
