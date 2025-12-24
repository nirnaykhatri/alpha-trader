/**
 * Order History Table Component
 * 
 * Professional data table for displaying order history with filtering,
 * sorting, and export capabilities.
 * 
 * @module components/tables/order-history
 */

'use client'

import React, { useState, useMemo } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Search,
  Filter,
  Download,
  MoreHorizontal,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Eye,
  XCircle,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react'

export type OrderStatus = 'filled' | 'partial' | 'pending' | 'cancelled' | 'rejected' | 'expired'
export type OrderSide = 'buy' | 'sell'
export type OrderType = 'market' | 'limit' | 'stop' | 'stop_limit'

export interface Order {
  id: string
  symbol: string
  side: OrderSide
  type: OrderType
  status: OrderStatus
  quantity: number
  filledQuantity: number
  price: number
  avgFillPrice?: number
  createdAt: string
  filledAt?: string
  pnl?: number
}

interface OrderHistoryProps {
  orders: Order[]
  isLoading?: boolean
  onCancelOrder?: (orderId: string) => Promise<void>
  onViewDetails?: (order: Order) => void
  onExport?: () => void
}

type SortDirection = 'asc' | 'desc' | null
type SortField = keyof Order

const statusConfig: Record<OrderStatus, { label: string; variant: 'default' | 'success' | 'danger' | 'warning' | 'secondary' }> = {
  filled: { label: 'Filled', variant: 'success' },
  partial: { label: 'Partial', variant: 'warning' },
  pending: { label: 'Pending', variant: 'default' },
  cancelled: { label: 'Cancelled', variant: 'secondary' },
  rejected: { label: 'Rejected', variant: 'danger' },
  expired: { label: 'Expired', variant: 'secondary' },
}

/**
 * Order History Component
 * 
 * @param {OrderHistoryProps} props - Component props
 * @returns {JSX.Element} Order history table
 */
export function OrderHistory({
  orders,
  isLoading = false,
  onCancelOrder,
  onViewDetails,
  onExport,
}: OrderHistoryProps): JSX.Element {
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<OrderStatus | 'all'>('all')
  const [sideFilter, setSideFilter] = useState<OrderSide | 'all'>('all')
  const [sortField, setSortField] = useState<SortField>('createdAt')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')
  const [currentPage, setCurrentPage] = useState(1)
  const pageSize = 20

  // Filter and sort orders
  const filteredOrders = useMemo(() => {
    let result = [...orders]

    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase()
      result = result.filter(
        (o) =>
          o.symbol.toLowerCase().includes(query) ||
          o.id.toLowerCase().includes(query)
      )
    }

    // Status filter
    if (statusFilter !== 'all') {
      result = result.filter((o) => o.status === statusFilter)
    }

    // Side filter
    if (sideFilter !== 'all') {
      result = result.filter((o) => o.side === sideFilter)
    }

    // Sort
    if (sortField && sortDirection) {
      result.sort((a, b) => {
        const aVal = a[sortField]
        const bVal = b[sortField]
        
        if (aVal === undefined || bVal === undefined) return 0
        
        let comparison = 0
        if (typeof aVal === 'string' && typeof bVal === 'string') {
          comparison = aVal.localeCompare(bVal)
        } else if (typeof aVal === 'number' && typeof bVal === 'number') {
          comparison = aVal - bVal
        }
        
        return sortDirection === 'desc' ? -comparison : comparison
      })
    }

    return result
  }, [orders, searchQuery, statusFilter, sideFilter, sortField, sortDirection])

  // Pagination
  const totalPages = Math.ceil(filteredOrders.length / pageSize)
  const paginatedOrders = filteredOrders.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  )

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((prev) => {
        if (prev === 'asc') return 'desc'
        if (prev === 'desc') return null
        return 'asc'
      })
    } else {
      setSortField(field)
      setSortDirection('asc')
    }
  }

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="h-4 w-4 ml-1" />
    if (sortDirection === 'asc') return <ArrowUp className="h-4 w-4 ml-1" />
    if (sortDirection === 'desc') return <ArrowDown className="h-4 w-4 ml-1" />
    return <ArrowUpDown className="h-4 w-4 ml-1" />
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Order History</CardTitle>
            <CardDescription>
              View and manage all trading orders
            </CardDescription>
          </div>
          <Button variant="outline" onClick={onExport} className="gap-2">
            <Download className="h-4 w-4" />
            Export
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Filters */}
        <div className="flex flex-wrap gap-4">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by symbol or order ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
          <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as OrderStatus | 'all')}>
            <SelectTrigger className="w-[140px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="filled">Filled</SelectItem>
              <SelectItem value="partial">Partial</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="cancelled">Cancelled</SelectItem>
              <SelectItem value="rejected">Rejected</SelectItem>
              <SelectItem value="expired">Expired</SelectItem>
            </SelectContent>
          </Select>
          <Select value={sideFilter} onValueChange={(v) => setSideFilter(v as OrderSide | 'all')}>
            <SelectTrigger className="w-[120px]">
              <SelectValue placeholder="Side" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Sides</SelectItem>
              <SelectItem value="buy">Buy</SelectItem>
              <SelectItem value="sell">Sell</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Table */}
        <div className="rounded-md border">
          <ScrollArea className="h-[600px]">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleSort('createdAt')}
                  >
                    <div className="flex items-center">
                      Date
                      <SortIcon field="createdAt" />
                    </div>
                  </TableHead>
                  <TableHead
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleSort('symbol')}
                  >
                    <div className="flex items-center">
                      Symbol
                      <SortIcon field="symbol" />
                    </div>
                  </TableHead>
                  <TableHead>Side</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead className="text-right">Qty</TableHead>
                  <TableHead className="text-right">Filled</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead className="text-right">Avg Fill</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">P&L</TableHead>
                  <TableHead className="w-[50px]" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  <TableRow>
                    <TableCell colSpan={11} className="h-24 text-center">
                      <RefreshCw className="h-6 w-6 animate-spin mx-auto text-muted-foreground" />
                    </TableCell>
                  </TableRow>
                ) : paginatedOrders.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={11} className="h-24 text-center text-muted-foreground">
                      No orders found
                    </TableCell>
                  </TableRow>
                ) : (
                  paginatedOrders.map((order) => (
                    <TableRow key={order.id} className="hover:bg-muted/30">
                      <TableCell className="font-mono text-xs">
                        {new Date(order.createdAt).toLocaleString()}
                      </TableCell>
                      <TableCell className="font-bold">{order.symbol}</TableCell>
                      <TableCell>
                        <Badge
                          variant={order.side === 'buy' ? 'success' : 'danger'}
                          className="uppercase"
                        >
                          {order.side}
                        </Badge>
                      </TableCell>
                      <TableCell className="capitalize">{order.type.replace('_', ' ')}</TableCell>
                      <TableCell className="text-right font-mono">{order.quantity}</TableCell>
                      <TableCell className="text-right font-mono">{order.filledQuantity}</TableCell>
                      <TableCell className="text-right font-mono">
                        ${order.price.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {order.avgFillPrice ? `$${order.avgFillPrice.toFixed(2)}` : '—'}
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusConfig[order.status].variant}>
                          {statusConfig[order.status].label}
                        </Badge>
                      </TableCell>
                      <TableCell
                        className={cn(
                          'text-right font-mono font-bold',
                          order.pnl && order.pnl > 0 && 'text-profit',
                          order.pnl && order.pnl < 0 && 'text-loss'
                        )}
                      >
                        {order.pnl !== undefined
                          ? `${order.pnl >= 0 ? '+' : ''}$${order.pnl.toFixed(2)}`
                          : '—'}
                      </TableCell>
                      <TableCell>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuLabel>Actions</DropdownMenuLabel>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem onClick={() => onViewDetails?.(order)}>
                              <Eye className="mr-2 h-4 w-4" />
                              View Details
                            </DropdownMenuItem>
                            {order.status === 'pending' && (
                              <DropdownMenuItem
                                className="text-loss focus:text-loss"
                                onClick={() => onCancelOrder?.(order.id)}
                              >
                                <XCircle className="mr-2 h-4 w-4" />
                                Cancel Order
                              </DropdownMenuItem>
                            )}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </ScrollArea>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Showing {((currentPage - 1) * pageSize) + 1} to{' '}
            {Math.min(currentPage * pageSize, filteredOrders.length)} of{' '}
            {filteredOrders.length} orders
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              onClick={() => setCurrentPage(1)}
              disabled={currentPage === 1}
            >
              <ChevronsLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              onClick={() => setCurrentPage((p) => p - 1)}
              disabled={currentPage === 1}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-sm px-4">
              Page {currentPage} of {totalPages || 1}
            </span>
            <Button
              variant="outline"
              size="icon"
              onClick={() => setCurrentPage((p) => p + 1)}
              disabled={currentPage >= totalPages}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              onClick={() => setCurrentPage(totalPages)}
              disabled={currentPage >= totalPages}
            >
              <ChevronsRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default OrderHistory
