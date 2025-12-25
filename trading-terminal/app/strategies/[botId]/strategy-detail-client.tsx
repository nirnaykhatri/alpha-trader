/**
 * Bot Strategy Detail Client Component
 * 
 * Client-side component for rendering individual bot strategy pages.
 * 
 * @module app/strategies/[botId]/strategy-detail-client
 */

'use client'

import React from 'react'
import Link from 'next/link'
import {
  Grid3X3,
  Layers,
  TrendingDown,
  Repeat,
  RefreshCw,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  TrendingUp,
  BarChart3,
  Shield,
  Zap,
  Target,
  Clock,
  DollarSign,
  LineChart,
  Activity,
  ChevronRight,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

// ============================================================================
// Types
// ============================================================================

interface BotStrategy {
  id: string
  name: string
  tagline: string
  description: string
  icon: React.ReactNode
  color: string
  bgGradient: string
  marketType: 'spot' | 'futures'
  badges: { label: string; variant: 'default' | 'success' | 'warning' | 'info' }[]
  benefits: {
    title: string
    description: string
    icon: React.ReactNode
  }[]
  features: string[]
  bestFor: string[]
  risks: string[]
  howItWorks: {
    step: number
    title: string
    description: string
  }[]
}

// ============================================================================
// Bot Strategy Data
// ============================================================================

const BOT_STRATEGIES: Record<string, BotStrategy> = {
  grid: {
    id: 'grid',
    name: 'GRID Bot',
    tagline: 'Profit from Every Price Movement',
    description: 'Generate profit from small price fluctuations as the market moves sideways. The GRID bot places a series of buy and sell orders at predetermined price levels, creating a "grid" of orders that captures gains from market volatility.',
    icon: <Grid3X3 className="h-8 w-8" />,
    color: 'text-blue-500',
    bgGradient: 'from-blue-500/20 to-blue-600/10',
    marketType: 'spot',
    badges: [
      { label: 'Sideways', variant: 'info' },
      { label: 'Spot', variant: 'success' },
      { label: 'Low Risk', variant: 'success' },
    ],
    benefits: [
      {
        title: 'Profit in Ranging Markets',
        description: 'Most markets move sideways 70% of the time. GRID bot capitalizes on this by generating continuous profits from small price movements.',
        icon: <BarChart3 className="h-5 w-5" />,
      },
      {
        title: 'Fully Automated',
        description: 'Set your price range and grid levels, then let the bot work 24/7. No need for constant monitoring or manual intervention.',
        icon: <Zap className="h-5 w-5" />,
      },
      {
        title: 'Instant Launch',
        description: 'Start trading in just a few clicks with ready-to-go templates or customize every setting to match your strategy.',
        icon: <Clock className="h-5 w-5" />,
      },
    ],
    features: [
      'Stop Loss & Take Profit',
      'Trailing Up & Down',
      'Pump/Dump Protection',
      'Backtest on Historical Data',
      'Base/Quote Currency Profit',
      'Customizable Grid Levels',
    ],
    bestFor: [
      'Sideways/ranging markets',
      'Stable trading pairs',
      'Traders who prefer lower risk',
      'Passive income generation',
    ],
    risks: [
      'May underperform in strong trending markets',
      'Requires sufficient capital to cover all grid levels',
      'Price moving outside the grid range stops trading',
    ],
    howItWorks: [
      { step: 1, title: 'Set Price Range', description: 'Define the upper and lower price boundaries where you expect the market to trade.' },
      { step: 2, title: 'Configure Grid', description: 'Set the number of grid levels. More levels = smaller profits per trade but more frequent trades.' },
      { step: 3, title: 'Bot Places Orders', description: 'The bot automatically places buy orders below current price and sell orders above.' },
      { step: 4, title: 'Capture Profits', description: 'As price oscillates, the bot buys low and sells high, accumulating profits from each completed cycle.' },
    ],
  },
  dca: {
    id: 'dca',
    name: 'DCA Bot',
    tagline: 'Low-Risk Earnings in Volatile Markets',
    description: 'Dollar Cost Averaging (DCA) is a time-tested investment strategy that reduces risk by spreading purchases across multiple price levels. When the price drops, the bot buys more, lowering your average cost. When it rises, you profit!',
    icon: <Layers className="h-8 w-8" />,
    color: 'text-green-500',
    bgGradient: 'from-green-500/20 to-green-600/10',
    marketType: 'spot',
    badges: [
      { label: 'Long', variant: 'success' },
      { label: 'Spot', variant: 'success' },
      { label: 'Beginner Friendly', variant: 'info' },
    ],
    benefits: [
      {
        title: 'Buy Cheaper via DCA Levels',
        description: 'The averaging strategy works perfectly on volatile crypto markets. Place up to 100 DCA orders to buy at progressively lower prices.',
        icon: <TrendingDown className="h-5 w-5" />,
      },
      {
        title: 'Works in Any Market',
        description: 'DCA bot can outperform buy & hold in falling, sideways, and rising markets. It\'s your Swiss Army knife for crypto trading.',
        icon: <Activity className="h-5 w-5" />,
      },
      {
        title: 'Advanced Risk Management',
        description: 'Built-in Stop Loss, Take Profit, and trailing features help protect your investment and lock in gains automatically.',
        icon: <Shield className="h-5 w-5" />,
      },
    ],
    features: [
      'Up to 100 DCA Orders',
      'Stop Loss & Take Profit',
      'Trailing Up & Down',
      'Pump/Dump Protection',
      'Technical Indicators Entry',
      'Multiplier for DCA Steps',
      'Manual Averaging Option',
      'Active Orders Limit',
    ],
    bestFor: [
      'Volatile market conditions',
      'Long-term position building',
      'Risk-averse traders',
      'Accumulating crypto over time',
    ],
    risks: [
      'Requires capital for all DCA levels',
      'Extended drawdowns in prolonged bear markets',
      'Opportunity cost while waiting for price recovery',
    ],
    howItWorks: [
      { step: 1, title: 'Set Base Order', description: 'Define your initial investment amount and the trading pair you want to trade.' },
      { step: 2, title: 'Configure DCA Levels', description: 'Set how many averaging orders to place and at what price intervals.' },
      { step: 3, title: 'Price Drops = More Buys', description: 'As the price falls, the bot automatically buys more at each DCA level, lowering your average cost.' },
      { step: 4, title: 'Take Profit', description: 'When price rises above your average cost + target profit, the bot sells and starts a new cycle.' },
    ],
  },
  btd: {
    id: 'btd',
    name: 'BTD Bot',
    tagline: 'Rising Yields from Falling Prices',
    description: 'Buy The Dip (BTD) bot monitors the market for sudden price drops and automatically buys when significant dips occur. This strategy is based on the concept that markets tend to recover after sharp declines, allowing you to buy low and sell high.',
    icon: <TrendingDown className="h-8 w-8" />,
    color: 'text-orange-500',
    bgGradient: 'from-orange-500/20 to-orange-600/10',
    marketType: 'spot',
    badges: [
      { label: 'Dip Buyer', variant: 'warning' },
      { label: 'Spot', variant: 'success' },
      { label: 'Contrarian', variant: 'info' },
    ],
    benefits: [
      {
        title: 'Seize the Opportunity',
        description: 'The BTD Bot monitors the market 24/7 and identifies sudden price drops, allowing you to buy at discounted prices automatically.',
        icon: <Target className="h-5 w-5" />,
      },
      {
        title: 'Stay Ahead of the Market',
        description: 'Take advantage of sudden price dips before the market corrects itself. The bot reacts faster than manual trading ever could.',
        icon: <Zap className="h-5 w-5" />,
      },
      {
        title: 'Reduce Emotional Trading',
        description: 'Automate the buying process during dips, removing fear and hesitation that often prevent traders from buying at the best prices.',
        icon: <Shield className="h-5 w-5" />,
      },
    ],
    features: [
      'Customizable Dip Detection',
      'Stop Loss & Take Profit',
      'Trailing Down',
      'Low/High Price Limits',
      'Demo Mode for Testing',
      'Backtest on Historical Data',
    ],
    bestFor: [
      'Contrarian traders',
      'Long-term investors',
      'Accumulating during corrections',
      'Markets with frequent dips',
    ],
    risks: [
      'May catch "falling knives" in prolonged downtrends',
      'Requires patience for recovery',
      'Capital tied up during extended dips',
    ],
    howItWorks: [
      { step: 1, title: 'Set Dip Parameters', description: 'Define what constitutes a "dip" - the percentage drop that triggers a buy order.' },
      { step: 2, title: 'Configure Buy Amount', description: 'Set how much to invest when a dip is detected and any price limits.' },
      { step: 3, title: 'Bot Monitors Market', description: 'The bot watches the market 24/7, waiting for the price to drop by your specified amount.' },
      { step: 4, title: 'Auto-Buy on Dip', description: 'When a qualifying dip occurs, the bot automatically executes your buy order and sets take profit.' },
    ],
  },
  spot_loop: {
    id: 'spot_loop',
    name: 'LOOP Bot',
    tagline: 'Profit Both Ways, Amplify Growth',
    description: 'The LOOP Bot is an advanced position trading tool that earns in both base and quote currencies while automatically reinvesting all profits back into active trades. This creates a compounding effect that accelerates portfolio growth.',
    icon: <Repeat className="h-8 w-8" />,
    color: 'text-purple-500',
    bgGradient: 'from-purple-500/20 to-purple-600/10',
    marketType: 'spot',
    badges: [
      { label: 'Sideways', variant: 'info' },
      { label: 'Reinvest', variant: 'success' },
      { label: 'Spot', variant: 'success' },
    ],
    benefits: [
      {
        title: 'Dual Currency Profits',
        description: 'Earn in both base and quote currencies as markets move. Fix profits in whichever currency suits you best.',
        icon: <DollarSign className="h-5 w-5" />,
      },
      {
        title: 'Auto-Reinvest for Growth',
        description: 'Every profit is automatically reinvested back into the bot, creating a snowball effect that compounds your gains over time.',
        icon: <TrendingUp className="h-5 w-5" />,
      },
      {
        title: 'Smart Price Adjustment',
        description: 'The bot dynamically adjusts price levels to avoid bad entries and capitalize on market swings.',
        icon: <LineChart className="h-5 w-5" />,
      },
    ],
    features: [
      'Base/Quote Profit + Exit',
      'Auto-Reinvest Profits',
      'Take Profit Targets',
      'Infinite Loop Trading',
      'Pre-made Strategies',
      'Transparent Analytics',
    ],
    bestFor: [
      'Long-term position trading',
      'Compound growth seekers',
      'Sideways/volatile markets',
      'Hands-off investors',
    ],
    risks: [
      'Extended price moves outside range reduce effectiveness',
      'Requires patience for compounding to show results',
      'Capital locked in active positions',
    ],
    howItWorks: [
      { step: 1, title: 'Set Price Range', description: 'Define the trading range where you expect price to oscillate.' },
      { step: 2, title: 'Configure Levels', description: 'Set up the grid levels and profit targets for each trade.' },
      { step: 3, title: 'Earn Both Ways', description: 'Profit in base currency when price falls below start, quote currency when it rises above.' },
      { step: 4, title: 'Auto-Compound', description: 'All profits are reinvested automatically, growing your position with each cycle.' },
    ],
  },
  futures_dca: {
    id: 'futures_dca',
    name: 'DCA Futures Bot',
    tagline: 'Structured Gains from Futures Volatility',
    description: 'Combine the proven DCA strategy with the power of futures leverage. Reduce risk through averaging while multiplying potential returns up to 10x. Perfect for traders who understand leverage and want enhanced returns.',
    icon: <Layers className="h-8 w-8" />,
    color: 'text-yellow-500',
    bgGradient: 'from-yellow-500/20 to-yellow-600/10',
    marketType: 'futures',
    badges: [
      { label: 'Futures', variant: 'warning' },
      { label: 'Leverage', variant: 'info' },
      { label: 'Advanced', variant: 'warning' },
    ],
    benefits: [
      {
        title: 'Navigate Futures with Precision',
        description: 'The DCA strategy helps manage the higher risks of futures trading by averaging into positions and using strict risk controls.',
        icon: <Target className="h-5 w-5" />,
      },
      {
        title: 'Multiply Your Potential',
        description: 'Use up to 10x leverage to amplify your returns. The DCA approach helps manage the additional risk that comes with leverage.',
        icon: <Zap className="h-5 w-5" />,
      },
      {
        title: 'Long or Short',
        description: 'Profit whether the market goes up or down. Open long positions in bullish markets or short positions in bearish conditions.',
        icon: <TrendingUp className="h-5 w-5" />,
      },
    ],
    features: [
      'Up to 10x Leverage',
      'Isolated/Cross Margin',
      'Stop Loss & Take Profit',
      'Trailing Up & Down',
      'Pump/Dump Protection',
      'Manual Averaging',
      'Technical Indicators',
      'Backtest Available',
    ],
    bestFor: [
      'Experienced traders',
      'Those comfortable with leverage',
      'Active market participants',
      'Traders seeking amplified returns',
    ],
    risks: [
      'Leverage amplifies both gains AND losses',
      'Liquidation risk if margin insufficient',
      'Higher volatility and faster position changes',
      'Funding fees on perpetual contracts',
    ],
    howItWorks: [
      { step: 1, title: 'Choose Direction', description: 'Decide to go Long (bullish) or Short (bearish) based on market analysis.' },
      { step: 2, title: 'Set Leverage & Margin', description: 'Configure leverage (1-10x) and choose isolated or cross margin mode.' },
      { step: 3, title: 'Configure DCA Levels', description: 'Set up your DCA orders to average into the position as price moves.' },
      { step: 4, title: 'Manage & Profit', description: 'Bot manages position with stop loss and take profit. Profits are in USDT.' },
    ],
  },
  futures_combo: {
    id: 'futures_combo',
    name: 'COMBO Bot',
    tagline: 'High Risks & Returns in Futures Trading',
    description: 'The ultimate futures trading bot combining GRID and DCA strategies. Uses DCA for buy orders (averaging down) and GRID for sell orders (taking profits at multiple levels). Leverage up to 10x for maximum potential returns.',
    icon: <RefreshCw className="h-8 w-8" />,
    color: 'text-red-500',
    bgGradient: 'from-red-500/20 to-red-600/10',
    marketType: 'futures',
    badges: [
      { label: 'Futures', variant: 'warning' },
      { label: 'High Risk', variant: 'warning' },
      { label: 'Leverage', variant: 'info' },
    ],
    benefits: [
      {
        title: 'Best of Both Worlds',
        description: 'Combines DCA averaging technique for entries with GRID profit-taking for exits. Get the benefits of both proven strategies.',
        icon: <RefreshCw className="h-5 w-5" />,
      },
      {
        title: 'Boost Trading 10x',
        description: 'Futures allow trading large borrowed amounts. Your P&L is magnified - profits come faster, but so do losses.',
        icon: <Zap className="h-5 w-5" />,
      },
      {
        title: 'Expert Strategies',
        description: 'Choose from pre-made profitable strategies tested on real data, or customize every parameter to your preference.',
        icon: <Target className="h-5 w-5" />,
      },
    ],
    features: [
      'DCA + GRID Hybrid Strategy',
      'Up to 10x Leverage',
      'Stop Loss & Take Profit',
      'Trailing Down',
      'Manual Averaging',
      'Backtest on Historical Data',
      'Long/Short Positions',
    ],
    bestFor: [
      'Risk-tolerant traders',
      'Those seeking maximum returns',
      'Experienced futures traders',
      'Active portfolio management',
    ],
    risks: [
      'Highest risk bot type - leverage amplifies losses',
      'Liquidation risk requires careful position sizing',
      'Not suitable for beginners',
      'Requires active monitoring',
    ],
    howItWorks: [
      { step: 1, title: 'Choose Direction', description: 'Select Long (profit when price rises) or Short (profit when price falls).' },
      { step: 2, title: 'Set Leverage & Capital', description: 'Configure leverage level and investment amount. Higher leverage = higher risk/reward.' },
      { step: 3, title: 'DCA Buys, GRID Sells', description: 'Bot uses DCA to build position at good prices, GRID to take profits at multiple levels.' },
      { step: 4, title: 'Compound Returns', description: 'Profits in USDT can be reinvested for accelerated growth.' },
    ],
  },
}

// Aliases for URL flexibility
const BOT_ALIASES: Record<string, string> = {
  'loop': 'spot_loop',
  'combo': 'futures_combo',
  'dca-futures': 'futures_dca',
}

// ============================================================================
// Props
// ============================================================================

interface StrategyDetailClientProps {
  botId: string
}

// ============================================================================
// Main Component
// ============================================================================

export default function StrategyDetailClient({ botId }: StrategyDetailClientProps) {
  // Handle aliases
  const resolvedBotId = BOT_ALIASES[botId] || botId
  const bot = BOT_STRATEGIES[resolvedBotId]

  if (!bot) {
    return (
      <div className="container mx-auto py-16 px-4 text-center">
        <h1 className="text-3xl font-bold mb-4">Strategy Not Found</h1>
        <p className="text-muted-foreground mb-8">
          The bot strategy &quot;{botId}&quot; doesn&apos;t exist. Please choose from our available strategies.
        </p>
        <Link href="/strategies">
          <Button>
            <ArrowLeft className="mr-2 h-4 w-4" />
            View All Strategies
          </Button>
        </Link>
      </div>
    )
  }

  return (
    <div className="container mx-auto py-8 px-4 max-w-5xl">
      {/* Back Button */}
      <Link href="/strategies">
        <Button variant="ghost" className="mb-6">
          <ArrowLeft className="mr-2 h-4 w-4" />
          All Strategies
        </Button>
      </Link>

      {/* Hero Section */}
      <div className={`relative rounded-xl p-8 bg-gradient-to-br ${bot.bgGradient} mb-8`}>
        <div className="flex items-start gap-6">
          <div className={`p-4 rounded-xl bg-background/90 ${bot.color}`}>
            {bot.icon}
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-3xl font-bold">{bot.name}</h1>
              <Badge variant={bot.marketType === 'futures' ? 'destructive' : 'secondary'}>
                {bot.marketType === 'futures' ? 'Futures' : 'Spot'}
              </Badge>
            </div>
            <p className="text-xl text-muted-foreground mb-4">{bot.tagline}</p>
            <div className="flex flex-wrap gap-2">
              {bot.badges.map((badge, i) => (
                <Badge
                  key={i}
                  variant="outline"
                  className={
                    badge.variant === 'success' ? 'bg-green-500/10 text-green-500 border-green-500/30' :
                    badge.variant === 'warning' ? 'bg-yellow-500/10 text-yellow-500 border-yellow-500/30' :
                    badge.variant === 'info' ? 'bg-blue-500/10 text-blue-500 border-blue-500/30' :
                    ''
                  }
                >
                  {badge.label}
                </Badge>
              ))}
            </div>
          </div>
        </div>
        <p className="mt-6 text-lg">{bot.description}</p>
      </div>

      {/* Benefits */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold mb-6">Key Benefits</h2>
        <div className="grid md:grid-cols-3 gap-6">
          {bot.benefits.map((benefit, i) => (
            <Card key={i} className="p-6">
              <div className={`p-3 rounded-lg bg-primary/10 w-fit mb-4 ${bot.color}`}>
                {benefit.icon}
              </div>
              <h3 className="text-lg font-semibold mb-2">{benefit.title}</h3>
              <p className="text-muted-foreground">{benefit.description}</p>
            </Card>
          ))}
        </div>
      </div>

      {/* How It Works */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold mb-6">How It Works</h2>
        <div className="grid md:grid-cols-4 gap-4">
          {bot.howItWorks.map((step, i) => (
            <div key={i} className="relative">
              <div className="flex items-center gap-3 mb-3">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center text-lg font-bold bg-primary/20 ${bot.color}`}>
                  {step.step}
                </div>
                {i < bot.howItWorks.length - 1 && (
                  <ChevronRight className="h-5 w-5 text-muted-foreground absolute -right-2 top-2 hidden md:block" />
                )}
              </div>
              <h3 className="font-semibold mb-1">{step.title}</h3>
              <p className="text-sm text-muted-foreground">{step.description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Features & Best For */}
      <div className="grid md:grid-cols-2 gap-6 mb-8">
        <Card className="p-6">
          <h3 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-green-500" />
            Features
          </h3>
          <ul className="space-y-2">
            {bot.features.map((feature, i) => (
              <li key={i} className="flex items-center gap-2 text-muted-foreground">
                <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
                {feature}
              </li>
            ))}
          </ul>
        </Card>

        <Card className="p-6">
          <h3 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <Target className="h-5 w-5 text-blue-500" />
            Best For
          </h3>
          <ul className="space-y-2">
            {bot.bestFor.map((item, i) => (
              <li key={i} className="flex items-center gap-2 text-muted-foreground">
                <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
                {item}
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {/* Risks */}
      <Card className="p-6 border-yellow-500/30 bg-yellow-500/5 mb-8">
        <h3 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-yellow-500" />
          Risks to Consider
        </h3>
        <ul className="space-y-2">
          {bot.risks.map((risk, i) => (
            <li key={i} className="flex items-start gap-2 text-muted-foreground">
              <div className="w-1.5 h-1.5 rounded-full bg-yellow-500 mt-2" />
              {risk}
            </li>
          ))}
        </ul>
      </Card>

      {/* CTA */}
      <div className="flex justify-center gap-4">
        <Link href="/strategies">
          <Button variant="outline" size="lg">
            <ArrowLeft className="mr-2 h-5 w-5" />
            View Other Strategies
          </Button>
        </Link>
        <Link href="/bots">
          <Button size="lg" className="px-8">
            Start Trading with {bot.name}
            <ArrowRight className="ml-2 h-5 w-5" />
          </Button>
        </Link>
      </div>
    </div>
  )
}
