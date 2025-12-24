/**
 * Fund Management Page
 * 
 * Deposit tracking, capital allocation, and fund management.
 * 
 * @module app/funds/page
 */

'use client'

import React, { useState } from 'react'
import { AppShell } from '@/components/layout'
import { ProtectedRoute } from '@/components/auth'
import { 
  Card, 
  CardContent, 
  CardHeader, 
  CardTitle, 
  Badge,
  Button,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui'
import { 
  Wallet, 
  TrendingUp, 
  TrendingDown, 
  ArrowUpRight,
  ArrowDownRight,
  PiggyBank,
  BarChart3,
  DollarSign,
  CreditCard,
  Building2,
  Plus,
  History,
  PieChart,
} from 'lucide-react'
import { formatCurrency } from '@/lib/utils'

/** Account balance information */
interface AccountBalance {
  cash: number
  marginUsed: number
  marginAvailable: number
  buyingPower: number
  portfolioValue: number
  totalEquity: number
  dayChange: number
  dayChangePercent: number
}

/** Fund transaction record */
interface FundTransaction {
  id: string
  date: string
  type: 'deposit' | 'withdrawal' | 'transfer' | 'dividend'
  amount: number
  status: 'completed' | 'pending' | 'failed'
  description: string
  method: string
}

/** Capital allocation by strategy */
interface AllocationItem {
  strategy: string
  allocated: number
  used: number
  available: number
  color: string
}

/** Mock account balance */
const mockBalance: AccountBalance = {
  cash: 32450.67,
  marginUsed: 82543.82,
  marginAvailable: 45000,
  buyingPower: 45000,
  portfolioValue: 127543.82,
  totalEquity: 159994.49,
  dayChange: 1234.56,
  dayChangePercent: 0.78,
}

/** Mock transactions */
const mockTransactions: FundTransaction[] = [
  { id: '1', date: '2024-03-15', type: 'deposit', amount: 10000, status: 'completed', description: 'Monthly deposit', method: 'ACH Transfer' },
  { id: '2', date: '2024-03-10', type: 'dividend', amount: 245.67, status: 'completed', description: 'AAPL dividend', method: 'Automatic' },
  { id: '3', date: '2024-03-05', type: 'deposit', amount: 5000, status: 'completed', description: 'Additional capital', method: 'Wire Transfer' },
  { id: '4', date: '2024-02-28', type: 'withdrawal', amount: 2000, status: 'completed', description: 'Profit withdrawal', method: 'ACH Transfer' },
  { id: '5', date: '2024-02-20', type: 'deposit', amount: 15000, status: 'completed', description: 'Initial funding', method: 'Wire Transfer' },
  { id: '6', date: '2024-03-16', type: 'deposit', amount: 3000, status: 'pending', description: 'Pending deposit', method: 'ACH Transfer' },
]

/** Mock allocations */
const mockAllocations: AllocationItem[] = [
  { strategy: 'DCA Long', allocated: 50000, used: 42500, available: 7500, color: 'bg-emerald-500' },
  { strategy: 'Momentum', allocated: 30000, used: 22500, available: 7500, color: 'bg-blue-500' },
  { strategy: 'Swing Trade', allocated: 25000, used: 17543.82, available: 7456.18, color: 'bg-purple-500' },
  { strategy: 'Reserve', allocated: 22543.82, used: 0, available: 22543.82, color: 'bg-gray-500' },
]

/**
 * BalanceOverview Component
 */
function BalanceOverview() {
  const isPositive = mockBalance.dayChange >= 0

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Total Equity
          </CardTitle>
          <DollarSign className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{formatCurrency(mockBalance.totalEquity)}</div>
          <p className={`text-xs ${isPositive ? 'text-emerald-500' : 'text-red-500'}`}>
            {isPositive ? '+' : ''}{formatCurrency(mockBalance.dayChange)} ({isPositive ? '+' : ''}{mockBalance.dayChangePercent}%)
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Cash Balance
          </CardTitle>
          <Wallet className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{formatCurrency(mockBalance.cash)}</div>
          <p className="text-xs text-muted-foreground">Available for trading</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Buying Power
          </CardTitle>
          <CreditCard className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{formatCurrency(mockBalance.buyingPower)}</div>
          <p className="text-xs text-muted-foreground">Including margin</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Portfolio Value
          </CardTitle>
          <PiggyBank className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{formatCurrency(mockBalance.portfolioValue)}</div>
          <p className="text-xs text-muted-foreground">Current positions</p>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * TransactionHistory Component
 */
function TransactionHistory() {
  const typeIcons = {
    deposit: <ArrowDownRight className="h-4 w-4 text-emerald-500" />,
    withdrawal: <ArrowUpRight className="h-4 w-4 text-red-500" />,
    transfer: <Building2 className="h-4 w-4 text-blue-500" />,
    dividend: <DollarSign className="h-4 w-4 text-purple-500" />,
  }

  const statusStyles = {
    completed: 'bg-emerald-500/10 text-emerald-500',
    pending: 'bg-yellow-500/10 text-yellow-500',
    failed: 'bg-red-500/10 text-red-500',
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <History className="h-5 w-5" />
            Transaction History
          </CardTitle>
          <Button variant="outline" size="sm">
            Export
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {mockTransactions.map((tx) => (
            <div 
              key={tx.id}
              className="flex items-center justify-between p-4 rounded-lg bg-muted/50 hover:bg-muted transition-colors"
            >
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-full bg-background flex items-center justify-center">
                  {typeIcons[tx.type]}
                </div>
                <div>
                  <p className="font-medium">{tx.description}</p>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span>{tx.date}</span>
                    <span>•</span>
                    <span>{tx.method}</span>
                  </div>
                </div>
              </div>
              <div className="text-right">
                <p className={`font-bold ${tx.type === 'withdrawal' ? 'text-red-500' : 'text-emerald-500'}`}>
                  {tx.type === 'withdrawal' ? '-' : '+'}{formatCurrency(tx.amount)}
                </p>
                <Badge className={statusStyles[tx.status]} variant="outline">
                  {tx.status}
                </Badge>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * AllocationChart Component
 */
function AllocationChart() {
  const total = mockAllocations.reduce((sum, item) => sum + item.allocated, 0)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <PieChart className="h-5 w-5" />
          Capital Allocation
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* Visual bar */}
        <div className="h-4 rounded-full overflow-hidden flex mb-6">
          {mockAllocations.map((item, index) => (
            <div
              key={item.strategy}
              className={`${item.color} transition-all`}
              style={{ width: `${(item.allocated / total) * 100}%` }}
            />
          ))}
        </div>

        {/* Allocation details */}
        <div className="space-y-4">
          {mockAllocations.map((item) => (
            <div key={item.strategy} className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className={`h-3 w-3 rounded-full ${item.color}`} />
                  <span className="font-medium">{item.strategy}</span>
                </div>
                <span className="text-sm text-muted-foreground">
                  {((item.allocated / total) * 100).toFixed(1)}%
                </span>
              </div>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Allocated</p>
                  <p className="font-medium">{formatCurrency(item.allocated)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Used</p>
                  <p className="font-medium">{formatCurrency(item.used)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Available</p>
                  <p className="font-medium text-emerald-500">{formatCurrency(item.available)}</p>
                </div>
              </div>
              <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                <div 
                  className={`h-full ${item.color} rounded-full`}
                  style={{ width: `${(item.used / item.allocated) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * DepositWithdrawDialog Component
 */
function DepositWithdrawDialog({ type }: { type: 'deposit' | 'withdraw' }) {
  const [amount, setAmount] = useState('')
  const [method, setMethod] = useState('ach')

  const isDeposit = type === 'deposit'

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant={isDeposit ? 'success' : 'danger'} className="gap-2">
          {isDeposit ? (
            <>
              <ArrowDownRight className="h-4 w-4" />
              Deposit
            </>
          ) : (
            <>
              <ArrowUpRight className="h-4 w-4" />
              Withdraw
            </>
          )}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{isDeposit ? 'Deposit Funds' : 'Withdraw Funds'}</DialogTitle>
          <DialogDescription>
            {isDeposit
              ? 'Add funds to your trading account.'
              : 'Withdraw funds from your trading account.'}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="amount">Amount</Label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
              <Input
                id="amount"
                type="number"
                placeholder="0.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="pl-7"
              />
            </div>
            {!isDeposit && (
              <p className="text-xs text-muted-foreground">
                Available: {formatCurrency(mockBalance.cash)}
              </p>
            )}
          </div>
          <div className="grid gap-2">
            <Label>Transfer Method</Label>
            <Select value={method} onValueChange={setMethod}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ach">ACH Transfer (2-3 business days)</SelectItem>
                <SelectItem value="wire">Wire Transfer (Same day)</SelectItem>
                {isDeposit && (
                  <SelectItem value="check">Check Deposit (5-7 business days)</SelectItem>
                )}
              </SelectContent>
            </Select>
          </div>
          {method === 'wire' && (
            <p className="text-xs text-yellow-500">
              Wire transfers may incur a $25 fee.
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline">Cancel</Button>
          <Button variant={isDeposit ? 'success' : 'danger'}>
            {isDeposit ? 'Deposit' : 'Withdraw'} Funds
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * QuickStats Component
 */
function QuickStats() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <BarChart3 className="h-5 w-5" />
          Margin Details
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Margin Used</span>
          <span className="font-medium">{formatCurrency(mockBalance.marginUsed)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Margin Available</span>
          <span className="font-medium text-emerald-500">{formatCurrency(mockBalance.marginAvailable)}</span>
        </div>
        <div className="h-2 bg-muted rounded-full overflow-hidden">
          <div 
            className="h-full bg-blue-500 rounded-full"
            style={{ width: `${(mockBalance.marginUsed / (mockBalance.marginUsed + mockBalance.marginAvailable)) * 100}%` }}
          />
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">Margin Usage</span>
          <span className="font-medium">
            {((mockBalance.marginUsed / (mockBalance.marginUsed + mockBalance.marginAvailable)) * 100).toFixed(1)}%
          </span>
        </div>
        <hr className="border-border" />
        <div className="flex justify-between">
          <span className="text-muted-foreground">Maintenance Requirement</span>
          <span className="font-medium">{formatCurrency(mockBalance.marginUsed * 0.25)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">SMA (Special Memo)</span>
          <span className="font-medium text-emerald-500">{formatCurrency(mockBalance.marginAvailable * 0.8)}</span>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Fund Management Page Component
 */
export default function FundsPage() {
  return (
    <ProtectedRoute>
      <AppShell>
        <div className="space-y-6">
          {/* Page Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">Fund Management</h1>
              <p className="text-muted-foreground">
                Manage your capital, deposits, and allocations
              </p>
            </div>
            <div className="flex items-center gap-3">
              <DepositWithdrawDialog type="withdraw" />
              <DepositWithdrawDialog type="deposit" />
            </div>
          </div>

          {/* Balance Overview */}
          <BalanceOverview />

          {/* Main Content */}
          <Tabs defaultValue="allocation" className="space-y-6">
            <TabsList>
              <TabsTrigger value="allocation">Capital Allocation</TabsTrigger>
              <TabsTrigger value="transactions">Transactions</TabsTrigger>
              <TabsTrigger value="margin">Margin Details</TabsTrigger>
            </TabsList>

            <TabsContent value="allocation">
              <div className="grid gap-6 lg:grid-cols-2">
                <AllocationChart />
                <QuickStats />
              </div>
            </TabsContent>

            <TabsContent value="transactions">
              <TransactionHistory />
            </TabsContent>

            <TabsContent value="margin">
              <div className="grid gap-6 lg:grid-cols-2">
                <QuickStats />
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Margin Call Prevention</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                      <div className="flex items-center gap-2 mb-2">
                        <Badge variant="success">Safe</Badge>
                        <span className="text-sm font-medium">No margin call risk</span>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Your equity is well above the maintenance requirement. 
                        Current buffer: {formatCurrency(mockBalance.marginAvailable)}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground mb-2">
                        Portfolio value would need to drop by <span className="font-medium text-foreground">35.2%</span> to trigger a margin call.
                      </p>
                      <div className="h-2 bg-muted rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-gradient-to-r from-emerald-500 via-yellow-500 to-red-500 rounded-full"
                          style={{ width: '64.8%' }}
                        />
                      </div>
                      <div className="flex justify-between text-xs text-muted-foreground mt-1">
                        <span>Current</span>
                        <span>Margin Call Threshold</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </AppShell>
    </ProtectedRoute>
  )
}
