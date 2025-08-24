# Multi-Broker Trading Bot Usage Examples
# ==========================================

# This file demonstrates how to use the new multi-broker abstraction system
# that was implemented for your trading bot.

## 1. CONFIGURATION EXAMPLE

"""
Update your config.yaml to support multiple brokers:

# Multi-Broker Configuration
brokers:
  # Primary broker (Alpaca)
  alpaca:
    enabled: true
    api_key: "${ALPACA_API_KEY}"
    secret_key: "${ALPACA_SECRET_KEY}"
    base_url: "https://paper-api.alpaca.markets"
    environment: "paper"
    
  # Future broker (Interactive Brokers)
  interactive_brokers:
    enabled: false  # Enable when ready
    account_id: "${IB_ACCOUNT_ID}"
    gateway_host: "localhost"
    gateway_port: 7497
    environment: "paper"
    
  # Mock broker for testing
  mock:
    enabled: false  # Enable for testing
    environment: "paper"
    additional_params:
      simulate_latency: true
      default_account_balance: 100000.0

# Symbol-to-Broker Routing
symbol_broker_mappings:
  # Route TSLA trades to Alpaca
  - symbol: "TSLA"
    broker_type: "alpaca"
    priority: 1
    is_primary: true
    extended_hours_enabled: true
    
  # Route AAPL trades to Interactive Brokers (when available)
  - symbol: "AAPL"
    broker_type: "interactive_brokers"
    priority: 1
    is_primary: true
    extended_hours_enabled: true
    
  # Route crypto or test symbols to mock broker
  - symbol: "BTCUSD"
    broker_type: "mock"
    priority: 1
    is_primary: true

# Broker Management Settings
broker_management:
  default_broker: "alpaca"  # Fallback broker
  health_check_interval_seconds: 30
  max_consecutive_failures: 3
  failover_enabled: true
"""

## 2. PYTHON CODE EXAMPLES

"""
# Initialize the multi-broker trading bot
from src.trading_bot import TradingBotOrchestrator

async def main():
    # Create bot instance
    bot = TradingBotOrchestrator("config.yaml")
    
    # Start the bot (now with multi-broker support)
    await bot.start()
    
    # The bot will automatically:
    # 1. Initialize all enabled brokers
    # 2. Set up symbol-to-broker routing
    # 3. Monitor broker health
    # 4. Route orders based on symbol mappings

# EXAMPLE 1: Submit orders to specific brokers
async def trade_different_symbols():
    bot = TradingBotOrchestrator()
    
    # This will route to Alpaca (based on config mapping)
    await bot.submit_order_via_broker("TSLA", "buy", 100)
    
    # This will route to Interactive Brokers (when configured)
    await bot.submit_order_via_broker("AAPL", "sell", 50)
    
    # This will route to mock broker (for testing)
    await bot.submit_order_via_broker("BTCUSD", "buy", 0.5)

# EXAMPLE 2: Monitor multi-broker positions
async def check_all_positions():
    bot = TradingBotOrchestrator()
    
    # Get positions across all brokers
    positions_by_broker = await bot.get_multi_broker_positions()
    
    # Results will look like:
    # {
    #   "alpaca": [
    #     {"symbol": "TSLA", "quantity": 100, "avg_cost": 250.0, ...}
    #   ],
    #   "interactive_brokers": [
    #     {"symbol": "AAPL", "quantity": -50, "avg_cost": 180.0, ...}
    #   ],
    #   "mock": [
    #     {"symbol": "BTCUSD", "quantity": 0.5, "avg_cost": 45000.0, ...}
    #   ]
    # }
    
    for broker_name, positions in positions_by_broker.items():
        print(f"Broker: {broker_name}")
        for pos in positions:
            print(f"  {pos['symbol']}: {pos['quantity']} @ ${pos['avg_cost']}")

# EXAMPLE 3: Monitor broker health
async def monitor_broker_health():
    bot = TradingBotOrchestrator()
    
    # Get health status of all brokers
    health_status = await bot.get_broker_health_status()
    
    # Results will look like:
    # {
    #   "alpaca": {
    #     "is_healthy": true,
    #     "consecutive_failures": 0,
    #     "last_health_check": "2025-08-24T12:34:56"
    #   },
    #   "interactive_brokers": {
    #     "is_healthy": false,
    #     "consecutive_failures": 3,
    #     "error_message": "Connection timeout"
    #   }
    # }
    
    for broker_name, health in health_status.items():
        status = "✅ Healthy" if health['is_healthy'] else "❌ Unhealthy"
        print(f"{broker_name}: {status}")
        if not health['is_healthy']:
            print(f"  Error: {health.get('error_message', 'Unknown')}")

# EXAMPLE 4: Get current prices from appropriate brokers
async def get_prices():
    bot = TradingBotOrchestrator()
    
    # These will automatically route to the correct broker
    tsla_price = await bot.get_current_price_via_broker("TSLA")  # → Alpaca
    aapl_price = await bot.get_current_price_via_broker("AAPL")  # → IB
    btc_price = await bot.get_current_price_via_broker("BTCUSD") # → Mock
    
    print(f"TSLA: ${tsla_price:.2f} (via Alpaca)")
    print(f"AAPL: ${aapl_price:.2f} (via Interactive Brokers)")
    print(f"BTCUSD: ${btc_price:.2f} (via Mock Broker)")

# EXAMPLE 5: Enhanced bot status with multi-broker info
async def check_bot_status():
    bot = TradingBotOrchestrator()
    
    status = await bot.get_status()
    
    # Status now includes broker manager information:
    # {
    #   "is_running": true,
    #   "positions": 5,
    #   "open_orders": 2,
    #   "broker_manager": {
    #     "available_brokers": ["alpaca", "mock"],
    #     "broker_count": 2,
    #     "broker_health": {
    #       "alpaca": {"is_healthy": true, "consecutive_failures": 0},
    #       "mock": {"is_healthy": true, "consecutive_failures": 0}
    #     }
    #   }
    # }
    
    print(f"Bot running: {status['is_running']}")
    print(f"Active brokers: {status['broker_manager']['available_brokers']}")
    print(f"Total positions: {status['positions']}")
"""

## 3. ADDING NEW BROKERS

"""
To add a new broker (e.g., TD Ameritrade), follow these steps:

1. Create a new broker adapter:
   src/brokers/td_ameritrade_broker.py

2. Implement the IBrokerProvider interface:
   
   class TDAmeritradeBrokerProvider(IBrokerProvider):
       def __init__(self, credentials: BrokerCredentials):
           # Initialize TD Ameritrade connection
           
       async def get_trading_client(self) -> ITradingClient:
           # Return TD Ameritrade trading client
           
       async def get_market_data_provider(self) -> IMarketDataProvider:
           # Return TD Ameritrade market data provider

3. Register the broker in BrokerFactory:
   # Add to src/core/broker_manager.py
   elif broker_type == BrokerType.TD_AMERITRADE:
       from ..brokers.td_ameritrade_broker import TDAmeritradeBrokerProvider
       return TDAmeritradeBrokerProvider(credentials)

4. Add to BrokerType enum:
   # Add to src/core/broker_interfaces.py
   TD_AMERITRADE = "td_ameritrade"

5. Configure in config.yaml:
   brokers:
     td_ameritrade:
       enabled: true
       client_id: "${TDA_CLIENT_ID}"
       refresh_token: "${TDA_REFRESH_TOKEN}"
       
6. Map symbols to the new broker:
   symbol_broker_mappings:
     - symbol: "SPY"
       broker_type: "td_ameritrade"
"""

## 4. TROUBLESHOOTING

"""
Common issues and solutions:

1. Import errors:
   - Ensure you're running from the project root directory
   - Check that all broker modules are in the src/ directory

2. Configuration errors:
   - Validate config.yaml syntax with a YAML validator
   - Ensure all required broker credentials are provided
   - Check that broker names match between config and code

3. Broker connection failures:
   - Check network connectivity
   - Verify API credentials are valid
   - Review broker-specific requirements (API keys, certificates, etc.)

4. Order routing issues:
   - Verify symbol_broker_mappings are correctly configured
   - Check that the target broker is enabled and healthy
   - Review logs for routing decisions

5. Testing:
   - Use the mock broker for development and testing
   - Enable verbose logging to see routing decisions
   - Use the broker health monitoring to identify issues
"""

print("📋 Multi-Broker Trading Bot Implementation Complete!")
print("🎯 Your bot can now route TSLA to Alpaca and AAPL to different brokers!")
print("📖 See the examples above for usage instructions.")
print()
print("🚀 Key files created:")
print("   • src/core/broker_interfaces.py - Universal broker interfaces")
print("   • src/core/broker_manager.py - Multi-broker management")
print("   • src/brokers/alpaca_broker.py - Alpaca adapter")
print("   • src/brokers/mock_broker.py - Mock broker for testing")
print("   • Updated src/trading_bot.py - Multi-broker orchestrator")
print("   • Enhanced config.yaml - Multi-broker configuration")