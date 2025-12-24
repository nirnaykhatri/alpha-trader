/**
 * Performance Charts Component
 * 
 * Beautiful, interactive charts for visualizing trading performance
 * including equity curve, P&L breakdown, win rate, and drawdown.
 * 
 * @module components/charts/performance-charts
 */

'use client'

import React, { useState, useMemo } from 'react'
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  ComposedChart,
} from 'recharts'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import {
  TrendingUp,
  TrendingDown,
  BarChart3,
  PieChart as PieChartIcon,
  Activity,
  DollarSign,
  Percent,
  Target,
  AlertTriangle,
} from 'lucide-react'

// Chart color constants using CSS variables
const COLORS = {
  profit: 'hsl(142, 76%, 36%)', // Green
  loss: 'hsl(0, 84%, 60%)', // Red
  primary: 'hsl(262, 83%, 58%)', // Purple
  secondary: 'hsl(217, 91%, 60%)', // Blue
  muted: 'hsl(215, 16%, 47%)', // Gray
  warning: 'hsl(45, 93%, 47%)', // Yellow
  grid: 'hsl(215, 20%, 20%)', // Grid lines
}

interface EquityDataPoint {
  date: string
  equity: number
  benchmark?: number
}

interface PnLDataPoint {
  date: string
  realized: number
  unrealized: number
  total: number
}

interface TradeDataPoint {
  date: string
  wins: number
  losses: number
  total: number
}

interface DrawdownDataPoint {
  date: string
  drawdown: number
  maxDrawdown: number
}

interface PerformanceData {
  equityCurve: EquityDataPoint[]
  dailyPnL: PnLDataPoint[]
  trades: TradeDataPoint[]
  drawdown: DrawdownDataPoint[]
  summary: {
    totalReturn: number
    totalPnL: number
    winRate: number
    avgWin: number
    avgLoss: number
    profitFactor: number
    sharpeRatio: number
    maxDrawdown: number
    totalTrades: number
    winningTrades: number
    losingTrades: number
  }
}

interface PerformanceChartsProps {
  data: PerformanceData
  isLoading?: boolean
}

type TimeRange = '1D' | '1W' | '1M' | '3M' | '6M' | '1Y' | 'ALL'

/**
 * Custom Tooltip for Charts
 */
function CustomTooltip({
  active,
  payload,
  label,
  formatter,
}: {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string }>
  label?: string
  formatter?: (value: number) => string
}) {
  if (!active || !payload?.length) return null

  return (
    <div className="rounded-lg border border-border bg-card p-3 shadow-xl">
      <p className="text-sm font-medium text-muted-foreground mb-2">{label}</p>
      {payload.map((entry, index) => (
        <div key={index} className="flex items-center justify-between gap-4 text-sm">
          <div className="flex items-center gap-2">
            <div
              className="h-3 w-3 rounded-full"
              style={{ backgroundColor: entry.color }}
            />
            <span className="text-muted-foreground">{entry.name}</span>
          </div>
          <span className="font-medium">
            {formatter ? formatter(entry.value) : `$${entry.value.toLocaleString()}`}
          </span>
        </div>
      ))}
    </div>
  )
}

/**
 * Summary Metric Card
 */
function MetricCard({
  title,
  value,
  change,
  icon,
  trend,
  format = 'number',
}: {
  title: string
  value: number
  change?: number
  icon: React.ReactNode
  trend?: 'up' | 'down' | 'neutral'
  format?: 'number' | 'currency' | 'percent' | 'ratio'
}) {
  const formattedValue = useMemo(() => {
    switch (format) {
      case 'currency':
        return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
      case 'percent':
        return `${value.toFixed(2)}%`
      case 'ratio':
        return value.toFixed(2)
      default:
        return value.toLocaleString()
    }
  }, [value, format])

  return (
    <div className="flex items-center gap-4 p-4 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors">
      <div
        className={cn(
          'p-3 rounded-lg',
          trend === 'up' && 'bg-profit/10 text-profit',
          trend === 'down' && 'bg-loss/10 text-loss',
          !trend && 'bg-primary/10 text-primary'
        )}
      >
        {icon}
      </div>
      <div>
        <p className="text-sm text-muted-foreground">{title}</p>
        <p
          className={cn(
            'text-xl font-bold',
            trend === 'up' && 'text-profit',
            trend === 'down' && 'text-loss'
          )}
        >
          {formattedValue}
        </p>
      </div>
    </div>
  )
}

/**
 * Equity Curve Chart
 */
function EquityCurveChart({ data }: { data: EquityDataPoint[] }) {
  const initialEquity = data[0]?.equity || 0

  return (
    <ResponsiveContainer width="100%" height={400}>
      <ComposedChart data={data}>
        <defs>
          <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={COLORS.primary} stopOpacity={0.3} />
            <stop offset="95%" stopColor={COLORS.primary} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} opacity={0.3} />
        <XAxis dataKey="date" stroke={COLORS.muted} fontSize={12} tickLine={false} />
        <YAxis
          stroke={COLORS.muted}
          fontSize={12}
          tickLine={false}
          tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
        />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine y={initialEquity} stroke={COLORS.muted} strokeDasharray="3 3" />
        <Area
          type="monotone"
          dataKey="equity"
          stroke={COLORS.primary}
          strokeWidth={2}
          fill="url(#equityGradient)"
          name="Equity"
        />
        {data[0]?.benchmark !== undefined && (
          <Line
            type="monotone"
            dataKey="benchmark"
            stroke={COLORS.secondary}
            strokeWidth={2}
            strokeDasharray="5 5"
            dot={false}
            name="Benchmark"
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/**
 * Daily P&L Bar Chart
 */
function DailyPnLChart({ data }: { data: PnLDataPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={350}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} opacity={0.3} />
        <XAxis dataKey="date" stroke={COLORS.muted} fontSize={12} tickLine={false} />
        <YAxis
          stroke={COLORS.muted}
          fontSize={12}
          tickLine={false}
          tickFormatter={(v) => `$${v}`}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend />
        <ReferenceLine y={0} stroke={COLORS.muted} />
        <Bar dataKey="total" name="Daily P&L">
          {data.map((entry, index) => (
            <Cell key={index} fill={entry.total >= 0 ? COLORS.profit : COLORS.loss} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/**
 * Win Rate Pie Chart
 */
function WinRateChart({
  wins,
  losses,
  winRate,
}: {
  wins: number
  losses: number
  winRate: number
}) {
  const data = [
    { name: 'Wins', value: wins, color: COLORS.profit },
    { name: 'Losses', value: losses, color: COLORS.loss },
  ]

  return (
    <div className="flex items-center justify-center gap-8">
      <ResponsiveContainer width={200} height={200}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={80}
            paddingAngle={5}
            dataKey="value"
          >
            {data.map((entry, index) => (
              <Cell key={index} fill={entry.color} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="space-y-4">
        <div className="text-center">
          <p className="text-4xl font-bold">{winRate.toFixed(1)}%</p>
          <p className="text-sm text-muted-foreground">Win Rate</p>
        </div>
        <div className="flex gap-6">
          <div className="text-center">
            <p className="text-2xl font-bold text-profit">{wins}</p>
            <p className="text-xs text-muted-foreground">Wins</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-loss">{losses}</p>
            <p className="text-xs text-muted-foreground">Losses</p>
          </div>
        </div>
      </div>
    </div>
  )
}

/**
 * Drawdown Chart
 */
function DrawdownChart({ data }: { data: DrawdownDataPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={250}>
      <AreaChart data={data}>
        <defs>
          <linearGradient id="drawdownGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={COLORS.loss} stopOpacity={0.4} />
            <stop offset="95%" stopColor={COLORS.loss} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} opacity={0.3} />
        <XAxis dataKey="date" stroke={COLORS.muted} fontSize={12} tickLine={false} />
        <YAxis
          stroke={COLORS.muted}
          fontSize={12}
          tickLine={false}
          tickFormatter={(v) => `${v}%`}
          reversed
        />
        <Tooltip
          content={
            <CustomTooltip formatter={(v) => `${Math.abs(v).toFixed(2)}%`} />
          }
        />
        <Area
          type="monotone"
          dataKey="drawdown"
          stroke={COLORS.loss}
          strokeWidth={2}
          fill="url(#drawdownGradient)"
          name="Drawdown"
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

/**
 * Performance Charts Component
 * 
 * @param {PerformanceChartsProps} props - Component props
 * @returns {JSX.Element} Performance charts dashboard
 */
export function PerformanceCharts({
  data,
  isLoading = false,
}: PerformanceChartsProps): JSX.Element {
  const [timeRange, setTimeRange] = useState<TimeRange>('1M')
  const [activeTab, setActiveTab] = useState('equity')

  const { summary } = data

  return (
    <div className="space-y-6">
      {/* Summary Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
        <MetricCard
          title="Total Return"
          value={summary.totalReturn}
          icon={<TrendingUp className="h-5 w-5" />}
          trend={summary.totalReturn >= 0 ? 'up' : 'down'}
          format="percent"
        />
        <MetricCard
          title="Total P&L"
          value={summary.totalPnL}
          icon={<DollarSign className="h-5 w-5" />}
          trend={summary.totalPnL >= 0 ? 'up' : 'down'}
          format="currency"
        />
        <MetricCard
          title="Win Rate"
          value={summary.winRate}
          icon={<Target className="h-5 w-5" />}
          format="percent"
        />
        <MetricCard
          title="Profit Factor"
          value={summary.profitFactor}
          icon={<BarChart3 className="h-5 w-5" />}
          trend={summary.profitFactor >= 1 ? 'up' : 'down'}
          format="ratio"
        />
        <MetricCard
          title="Max Drawdown"
          value={summary.maxDrawdown}
          icon={<AlertTriangle className="h-5 w-5" />}
          trend="down"
          format="percent"
        />
      </div>

      {/* Chart Tabs */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Performance Analytics</CardTitle>
            <CardDescription>Detailed visualization of trading performance</CardDescription>
          </div>
          <Select value={timeRange} onValueChange={(v) => setTimeRange(v as TimeRange)}>
            <SelectTrigger className="w-24">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1D">1D</SelectItem>
              <SelectItem value="1W">1W</SelectItem>
              <SelectItem value="1M">1M</SelectItem>
              <SelectItem value="3M">3M</SelectItem>
              <SelectItem value="6M">6M</SelectItem>
              <SelectItem value="1Y">1Y</SelectItem>
              <SelectItem value="ALL">All</SelectItem>
            </SelectContent>
          </Select>
        </CardHeader>
        <CardContent>
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="mb-6">
              <TabsTrigger value="equity" className="gap-2">
                <Activity className="h-4 w-4" />
                Equity Curve
              </TabsTrigger>
              <TabsTrigger value="pnl" className="gap-2">
                <BarChart3 className="h-4 w-4" />
                Daily P&L
              </TabsTrigger>
              <TabsTrigger value="winrate" className="gap-2">
                <PieChartIcon className="h-4 w-4" />
                Win Rate
              </TabsTrigger>
              <TabsTrigger value="drawdown" className="gap-2">
                <TrendingDown className="h-4 w-4" />
                Drawdown
              </TabsTrigger>
            </TabsList>

            <TabsContent value="equity">
              <EquityCurveChart data={data.equityCurve} />
            </TabsContent>

            <TabsContent value="pnl">
              <DailyPnLChart data={data.dailyPnL} />
            </TabsContent>

            <TabsContent value="winrate">
              <div className="py-8">
                <WinRateChart
                  wins={summary.winningTrades}
                  losses={summary.losingTrades}
                  winRate={summary.winRate}
                />
              </div>
            </TabsContent>

            <TabsContent value="drawdown">
              <DrawdownChart data={data.drawdown} />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      {/* Additional Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Trade Statistics</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Total Trades</span>
              <span className="font-bold">{summary.totalTrades}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Winning Trades</span>
              <span className="font-bold text-profit">{summary.winningTrades}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Losing Trades</span>
              <span className="font-bold text-loss">{summary.losingTrades}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Average Win</span>
              <span className="font-bold text-profit">
                ${summary.avgWin.toLocaleString()}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Average Loss</span>
              <span className="font-bold text-loss">
                ${Math.abs(summary.avgLoss).toLocaleString()}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Risk Metrics</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Sharpe Ratio</span>
              <Badge variant={summary.sharpeRatio >= 1 ? 'success' : 'warning'}>
                {summary.sharpeRatio.toFixed(2)}
              </Badge>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Profit Factor</span>
              <Badge variant={summary.profitFactor >= 1.5 ? 'success' : 'warning'}>
                {summary.profitFactor.toFixed(2)}
              </Badge>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Max Drawdown</span>
              <Badge variant={Math.abs(summary.maxDrawdown) < 10 ? 'success' : 'danger'}>
                {summary.maxDrawdown.toFixed(2)}%
              </Badge>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Win Rate</span>
              <Badge variant={summary.winRate >= 50 ? 'success' : 'warning'}>
                {summary.winRate.toFixed(1)}%
              </Badge>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export default PerformanceCharts
