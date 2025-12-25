/**
 * Individual Bot Strategy Page (Server Component)
 * 
 * Dynamic route for viewing details of a specific bot strategy.
 * Accessible via /strategies/[botId] (e.g., /strategies/dca, /strategies/grid)
 * 
 * This is a server component that exports generateStaticParams() for static export
 * and renders the client component with the botId.
 * 
 * @module app/strategies/[botId]/page
 */

import StrategyDetailClient from './strategy-detail-client'

// ============================================================================
// Static Params for Export
// ============================================================================

/**
 * Generate static params for all bot strategy pages.
 * Required for Next.js static export with dynamic routes.
 */
export function generateStaticParams() {
  return [
    { botId: 'grid' },
    { botId: 'dca' },
    { botId: 'btd' },
    { botId: 'spot_loop' },
    { botId: 'futures_dca' },
    { botId: 'futures_combo' },
    // Aliases
    { botId: 'loop' },
    { botId: 'combo' },
    { botId: 'dca-futures' },
  ]
}

// ============================================================================
// Page Component
// ============================================================================

interface PageProps {
  params: {
    botId: string
  }
}

export default function BotStrategyDetailPage({ params }: PageProps) {
  return <StrategyDetailClient botId={params.botId} />
}
