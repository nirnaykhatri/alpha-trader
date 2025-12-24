# Trading Terminal

Real-time trading dashboard for the Alpha Trader bot, built with Next.js 14 and shadcn/ui.

## Features

- 📊 Real-time position monitoring
- 💰 P&L tracking with visual indicators
- 🔄 Live updates via Azure SignalR
- 📱 Responsive design
- 🌙 Dark mode by default

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Styling**: Tailwind CSS + shadcn/ui
- **Real-time**: Azure SignalR
- **Charts**: Recharts + Lightweight Charts
- **Deployment**: Azure Static Web Apps

## Getting Started

### Prerequisites

- Node.js 20+
- npm or pnpm

### Installation

```bash
# Install dependencies
npm install

# Run development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to view the dashboard.

### Environment Variables

Create a `.env.local` file:

```env
NEXT_PUBLIC_API_URL=http://localhost:8080
NEXT_PUBLIC_SIGNALR_URL=https://your-signalr.service.signalr.net
NEXT_PUBLIC_ENVIRONMENT=development
```

## Project Structure

```
trading-terminal/
├── app/                    # Next.js App Router
│   ├── layout.tsx         # Root layout
│   ├── page.tsx           # Dashboard page
│   └── globals.css        # Global styles
├── components/            # React components
│   ├── position-card.tsx  # Position display
│   └── stats-card.tsx     # Statistics card
├── lib/                   # Utilities
│   ├── api.ts             # API client
│   ├── utils.ts           # Helper functions
│   └── hooks/             # React hooks
│       ├── use-trading.ts # Trading data hook
│       └── use-signalr.ts # SignalR connection
└── public/                # Static assets
```

## Deployment

This app is configured for Azure Static Web Apps with static export:

```bash
# Build for production
npm run build

# The 'out' directory contains the static files
```

## API Integration

The dashboard connects to the trading bot's REST API:

- `GET /positions` - Get all open positions
- `GET /portfolio-summary` - Get portfolio statistics
- `GET /orders` - Get recent orders
- `GET /health` - Health check endpoint

## License

MIT
