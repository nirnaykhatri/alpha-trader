"""
Market data provider implementation using Alpaca API.
Provides current and historical market data for trading decisions.
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from src.interfaces import IMarketDataProvider, IConfigurationManager
from src.exceptions import MarketDataException
from src.core.logging_config import get_logger


logger = get_logger(__name__)


class AlpacaMarketDataProvider(IMarketDataProvider):
    """
    Market data provider using Alpaca API.
    Provides both current and historical market data.
    """
    
    def __init__(self, config: IConfigurationManager):
        """
        Initialize market data provider.
        
        Args:
            config: Configuration manager instance
        """
        self._config = config
        
        # Initialize Alpaca data client
        api_key = config.get_config("api.alpaca.api_key")
        secret_key = config.get_config("api.alpaca.secret_key")
        
        if not api_key or not secret_key:
            raise MarketDataException("Alpaca API credentials not configured")
        
        self._client = StockHistoricalDataClient(api_key, secret_key)
        self._price_cache: Dict[str, Dict] = {}
        self._cache_duration = timedelta(seconds=2)  # Minimal 2-second cache for real-time accuracy
        
        # Initialize real-time data client for current prices
        try:
            from alpaca.data.live import StockDataStream
            from alpaca.data.requests import StockLatestQuoteRequest
            from alpaca.data.live.stock import StockDataStream
            # We'll use the historical client for now, but with minimal caching
        except ImportError:
            logger.warning("Real-time data client not available, using historical data")
        
        logger.info("AlpacaMarketDataProvider initialized")
    
    async def get_current_price(self, symbol: str) -> float:
        """
        Get the most recent available price for a symbol with enhanced real-time accuracy.
        Prioritizes latest quote/trade APIs for real-time data, especially during extended hours.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Most recent available price
            
        Raises:
            MarketDataException: If price data is unavailable
        """
        try:
            logger.debug(f"🔍 Fetching real-time price for {symbol}")
            
            # Check cache first, but with very short expiry for critical accuracy
            cache_key = f"price_{symbol}"
            cached_price = self._get_cached_price(cache_key)
            if cached_price:
                logger.debug(f"📋 Using cached price for {symbol}: ${cached_price:.4f}")
                return cached_price
            
            current_price = None
            data_source = None
            best_timestamp = None
            price_age_seconds = None
            
            # Get current time for age calculations
            from datetime import datetime, timezone
            now_utc = datetime.now(timezone.utc)
            
            # Collect data from all sources and pick the most recent (multi-candidate approach)
            all_candidates = []
            
            # STRATEGY 1: Latest Quote API - Real-time quotes (includes extended hours)
            try:
                quote_price = await self._get_latest_quote_price(symbol)
                if quote_price:
                    # Extract quote timestamp for comparison
                    from alpaca.data.requests import StockLatestQuoteRequest
                    request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(None, self._client.get_stock_latest_quote, request)
                    if response and symbol in response:
                        quote = response[symbol]
                        quote_time = quote.timestamp.replace(tzinfo=timezone.utc) if quote.timestamp.tzinfo is None else quote.timestamp
                        price_age_seconds = (now_utc - quote_time).total_seconds()
                        
                        all_candidates.append({
                            'price': quote_price,
                            'timestamp': quote_time,
                            'age_seconds': price_age_seconds,
                            'source': 'latest_quote_enhanced',
                            'data': f"Enhanced quote method: ${quote_price:.4f}"
                        })
                        logger.info(f"🎯 Enhanced quote for {symbol}: ${quote_price:.4f}")
                        
            except Exception as e:
                logger.debug(f"❌ Enhanced latest quote API failed for {symbol}: {e}")
                
                # Fallback to original quote method
            try:
                from alpaca.data.requests import StockLatestQuoteRequest
                
                request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(None, self._client.get_stock_latest_quote, request)
                
                if response and symbol in response:
                    quote = response[symbol]
                    logger.debug(f"📡 Latest quote response for {symbol}: {quote}")
                    
                    # Calculate quote age
                    from datetime import datetime, timezone
                    now_utc = datetime.now(timezone.utc)
                    quote_time = quote.timestamp.replace(tzinfo=timezone.utc) if quote.timestamp.tzinfo is None else quote.timestamp
                    price_age_seconds = (now_utc - quote_time).total_seconds()
                    
                    # Enhanced bid/ask validation for extended hours
                    bid_price = float(quote.bid_price) if quote.bid_price and quote.bid_price > 0 else None
                    ask_price = float(quote.ask_price) if quote.ask_price and quote.ask_price > 0 else None
                    
                    # Additional validation for unreasonable quotes
                    if bid_price and ask_price:
                        spread = ask_price - bid_price
                        spread_percentage = (spread / bid_price) * 100 if bid_price > 0 else 100
                        
                        # Flag wide spreads that might indicate stale/invalid extended hours quotes
                        if spread_percentage > 50:  # Spread > 50% of bid price
                            logger.warning(f"⚠️ Very wide spread for {symbol}: bid=${bid_price:.4f}, ask=${ask_price:.4f} (spread: {spread_percentage:.1f}%)")
                            logger.warning(f"   This might indicate stale extended hours quote data")
                        
                        quote_price = (bid_price + ask_price) / 2.0
                        all_candidates.append({
                            'price': quote_price,
                            'timestamp': quote_time,
                            'age_seconds': price_age_seconds,
                            'source': 'latest_quote_mid',
                            'data': f"bid=${bid_price:.4f}, ask=${ask_price:.4f}, mid=${quote_price:.4f}, spread={spread_percentage:.1f}%"
                        })
                        logger.info(f"🎯 Real-time quote for {symbol}: bid=${bid_price:.4f}, ask=${ask_price:.4f}, mid=${quote_price:.4f} (spread: {spread_percentage:.1f}%)")
                    elif bid_price and not ask_price:
                        logger.warning(f"⚠️ Quote for {symbol} has bid (${bid_price:.4f}) but ask=0 or missing - using bid only")
                        all_candidates.append({
                            'price': bid_price,
                            'timestamp': quote_time,
                            'age_seconds': price_age_seconds,
                            'source': 'latest_quote_bid',
                            'data': f"bid=${bid_price:.4f} (ask=0 or missing)"
                        })
                        logger.info(f"🎯 Real-time bid for {symbol}: ${bid_price:.4f} (ask=0 or missing)")
                    elif ask_price and not bid_price:
                        logger.warning(f"⚠️ Quote for {symbol} has ask (${ask_price:.4f}) but bid=0 or missing - using ask only")
                        all_candidates.append({
                            'price': ask_price,
                            'timestamp': quote_time,
                            'age_seconds': price_age_seconds,
                            'source': 'latest_quote_ask',
                            'data': f"ask=${ask_price:.4f} (bid=0 or missing)"
                        })
                        logger.info(f"🎯 Real-time ask for {symbol}: ${ask_price:.4f} (bid=0 or missing)")
                    else:
                        logger.warning(f"⚠️ Quote for {symbol} has both bid=0 and ask=0 - skipping quote data")
                        logger.debug(f"   Raw quote: bid_price={quote.bid_price}, ask_price={quote.ask_price}")
                    
                    if all_candidates:
                        logger.debug(f"✅ Quote success: ${all_candidates[-1]['price']:.4f} at {quote_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                
            except Exception as e:
                logger.debug(f"❌ Latest quote API failed for {symbol}: {e}")
            
            # STRATEGY 2: Latest Trade API - Most recent actual trades (includes extended hours)
            try:
                trade_price = await self._get_latest_trade_price(symbol)
                if trade_price:
                    # Extract trade timestamp for comparison
                    from alpaca.data.requests import StockLatestTradeRequest
                    request = StockLatestTradeRequest(symbol_or_symbols=symbol)
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(None, self._client.get_stock_latest_trade, request)
                    if response and symbol in response:
                        trade = response[symbol]
                        trade_time = trade.timestamp.replace(tzinfo=timezone.utc) if trade.timestamp.tzinfo is None else trade.timestamp
                        trade_age_seconds = (now_utc - trade_time).total_seconds()
                        
                        all_candidates.append({
                            'price': trade_price,
                            'timestamp': trade_time,
                            'age_seconds': trade_age_seconds,
                            'source': 'latest_trade_enhanced',
                            'data': f"Enhanced trade method: ${trade_price:.4f}"
                        })
                        logger.info(f"🎯 Enhanced trade for {symbol}: ${trade_price:.4f}")
                        
            except Exception as e:
                logger.debug(f"❌ Enhanced latest trade API failed for {symbol}: {e}")
                
                # Fallback to original trade method
            try:
                from alpaca.data.requests import StockLatestTradeRequest
                
                request = StockLatestTradeRequest(symbol_or_symbols=symbol)
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(None, self._client.get_stock_latest_trade, request)
                
                if response and symbol in response:
                    trade = response[symbol]
                    logger.debug(f"📡 Latest trade response for {symbol}: {trade}")
                    
                    if hasattr(trade, 'price') and trade.price and trade.price > 0:
                        trade_price = float(trade.price)
                        
                        # Calculate trade age
                        trade_time = trade.timestamp.replace(tzinfo=timezone.utc) if trade.timestamp.tzinfo is None else trade.timestamp
                        trade_age_seconds = (now_utc - trade_time).total_seconds()
                        
                        all_candidates.append({
                            'price': trade_price,
                            'timestamp': trade_time,
                            'age_seconds': trade_age_seconds,
                            'source': 'latest_trade',
                            'data': f"${trade_price:.4f} (size: {getattr(trade, 'size', 'unknown')})"
                        })
                        
                        logger.info(f"🎯 Latest trade for {symbol}: ${trade_price:.4f} at {trade_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                        
                        logger.debug(f"✅ Trade success: ${trade_price:.4f} at {trade_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                
            except Exception as e:
                logger.debug(f"❌ Latest trade API failed for {symbol}: {e}")
            
            # STRATEGY 3: Recent 1-minute bars - Often has more current extended hours data
            # This strategy is crucial for after-hours trading where quotes/trades may be stale
            try:
                logger.debug(f"📊 Checking recent bars for {symbol} (may have newer extended hours data)")
                # For extended hours, use high bar limit to capture the absolute latest data
                bars = await self._get_recent_bars_extended(symbol, "1Min", 1000, hours=24)  # High limit to get most recent data
                if bars:
                    latest_bar = bars[-1]
                    bar_price = latest_bar['close']
                    
                    # Calculate bar age
                    bar_time = latest_bar['timestamp'].replace(tzinfo=timezone.utc) if latest_bar['timestamp'].tzinfo is None else latest_bar['timestamp']
                    bar_age_seconds = (now_utc - bar_time).total_seconds()
                    
                    all_candidates.append({
                        'price': bar_price,
                        'timestamp': bar_time,
                        'age_seconds': bar_age_seconds,
                        'source': '1min_bars_extended_hours',
                        'data': f"${bar_price:.4f} from 1min bar"
                    })
                    
                    # Compare with quote/trade data - use bars if they're newer
                    quote_trade_candidates = [c for c in all_candidates if 'quote' in c['source'] or 'trade' in c['source']]
                    if quote_trade_candidates:
                        best_qt = min(quote_trade_candidates, key=lambda x: x['age_seconds'])
                        if bar_age_seconds < best_qt['age_seconds']:
                            logger.info(f"🎯 FOUND NEWER EXTENDED HOURS DATA for {symbol}!")
                            logger.info(f"   Quote/Trade: ${best_qt['price']:.4f} (age: {best_qt['age_seconds']:.0f}s)")
                            logger.info(f"   Recent Bar:  ${bar_price:.4f} (age: {bar_age_seconds:.0f}s)")
                            
                        logger.info(f"✅ Using extended hours bar data for {symbol}: ${bar_price:.4f} at {bar_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    
                    logger.debug(f"📊 Recent 1min bar for {symbol}: ${bar_price:.4f} at {bar_time.strftime('%Y-%m-%d %H:%M:%S UTC')} (age: {bar_age_seconds:.0f}s)")

            except Exception as e:
                logger.debug(f"❌ Recent bars failed for {symbol}: {e}")
            
            # Select the best price from all candidates using intelligent freshness scoring
            if all_candidates:
                # Check if we're in extended hours
                from datetime import datetime, timezone
                import pytz
                et = pytz.timezone('US/Eastern')
                now_et = datetime.now(et)
                hour_et = now_et.hour
                
                # If after hours (after 4 PM ET or before 9:30 AM ET)
                is_extended_hours = hour_et >= 16 or hour_et < 9
                logger.debug(f"⏰ Extended hours check: {now_et.strftime('%H:%M ET')} - Extended hours: {is_extended_hours}")
                
                # Calculate freshness score for each candidate
                # Score = (base score) + (context bonus) - (age penalty)
                def calculate_freshness_score(candidate):
                    age_hours = candidate['age_seconds'] / 3600
                    
                    # Base scores by data type
                    if 'quote' in candidate['source']:
                        base_score = 100  # Quotes are generally most current
                    elif 'trade' in candidate['source']:
                        base_score = 95   # Trades are actual transactions
                    elif 'bars' in candidate['source']:
                        base_score = 80   # Bars aggregate data over time
                    else:
                        base_score = 50   # Other sources
                    
                    # Context bonus during extended hours
                    context_bonus = 0
                    if is_extended_hours and 'bars' in candidate['source']:
                        # Bar data gets bonus during extended hours if it's reasonably fresh
                        if age_hours < 6:  # Within 6 hours
                            context_bonus = 25  # Increased bonus for bar data
                        elif age_hours < 12:  # Within 12 hours
                            context_bonus = 15  # Moderate bonus
                            
                        # Additional bonus if quotes/trades appear to be from market close
                        # Check if other candidates are from exactly 3:59:59 PM or 4:00:00 PM ET
                        quote_trade_candidates = [c for c in all_candidates if 'quote' in c['source'] or 'trade' in c['source']]
                        if quote_trade_candidates:
                            import pytz
                            et = pytz.timezone('US/Eastern')
                            for qt_candidate in quote_trade_candidates:
                                if hasattr(qt_candidate, 'timestamp') and qt_candidate['timestamp']:
                                    qt_time_et = qt_candidate['timestamp'].astimezone(et)
                                    # If quote/trade is from market close time, prefer bars
                                    if (qt_time_et.hour == 15 and qt_time_et.minute == 59) or (qt_time_et.hour == 16 and qt_time_et.minute == 0):
                                        context_bonus += 30  # Strong preference for bar data over market close data
                                        logger.debug(f"🕐 Detected market close data in quotes - boosting bar score by +30")
                                        break
                    
                    # Age penalty (more severe for older data)
                    if age_hours < 1:
                        age_penalty = 0
                    elif age_hours < 4:
                        age_penalty = age_hours * 5  # 5 points per hour
                    elif age_hours < 8:
                        age_penalty = 20 + (age_hours - 4) * 10  # 10 points per hour after 4h
                    else:
                        age_penalty = 60 + (age_hours - 8) * 15  # 15 points per hour after 8h
                    
                    final_score = base_score + context_bonus - age_penalty
                    return final_score
                
                # Score all candidates
                scored_candidates = []
                for candidate in all_candidates:
                    score = calculate_freshness_score(candidate)
                    
                    # Additional market close detection bonus for bar data
                    if is_extended_hours and 'bars' in candidate['source']:
                        # Check if we have quote/trade data from market close
                        quote_trade_candidates = [c for c in all_candidates if 'quote' in c['source'] or 'trade' in c['source']]
                        if quote_trade_candidates:
                            import pytz
                            et = pytz.timezone('US/Eastern')
                            for qt_candidate in quote_trade_candidates:
                                qt_time_et = qt_candidate['timestamp'].astimezone(et)
                                # If quote/trade is from market close time (3:59 PM ET), prefer bars
                                if qt_time_et.hour == 15 and qt_time_et.minute == 59:
                                    score += 50  # Major bonus for bar data when quotes are from market close
                                    logger.info(f"🕐 MARKET CLOSE DETECTED: Quote from {qt_time_et.strftime('%H:%M ET')} - boosting bar score by +50")
                                    break
                    
                    scored_candidates.append({
                        **candidate,
                        'freshness_score': score
                    })
                    age_hours = candidate['age_seconds'] / 3600
                    logger.debug(f"📊 {candidate['source']}: ${candidate['price']:.4f} (age: {age_hours:.1f}h, score: {score:.1f})")
                
                # Select the candidate with the highest freshness score
                best_candidate = max(scored_candidates, key=lambda x: x['freshness_score'])
                
                age_hours = best_candidate['age_seconds'] / 3600
                logger.info(f"🏆 Best candidate: {best_candidate['source']} = ${best_candidate['price']:.4f}")
                logger.info(f"   📈 Freshness score: {best_candidate['freshness_score']:.1f} (age: {age_hours:.1f}h)")
                
                # Show comparison with other candidates if there were multiple viable options
                other_candidates = [c for c in scored_candidates if c != best_candidate and c['freshness_score'] > 50]
                if other_candidates:
                    logger.debug("🔍 Other candidates considered:")
                    for candidate in sorted(other_candidates, key=lambda x: x['freshness_score'], reverse=True)[:2]:
                        cand_age_hours = candidate['age_seconds'] / 3600
                        logger.debug(f"   {candidate['source']}: ${candidate['price']:.4f} (age: {cand_age_hours:.1f}h, score: {candidate['freshness_score']:.1f})")
                
                current_price = best_candidate['price']
                data_source = best_candidate['source']
                price_age_seconds = best_candidate['age_seconds']
            
            # FALLBACK STRATEGY 4: 5-minute bars if no recent data
            if not current_price:
                try:
                    bars = await self._get_recent_bars_extended(symbol, "5Min", 20, hours=6)
                    if bars:
                        latest_bar = bars[-1]
                        current_price = latest_bar['close']
                        data_source = f"5min_bars"
                        logger.info(f"📊 Using 5min bars for {symbol}: ${current_price:.4f}")
                except Exception as e:
                    logger.debug(f"❌ 5min bars fallback failed for {symbol}: {e}")
            
            # FALLBACK STRATEGY 5: Daily bars as last resort
            if not current_price:
                try:
                    bars = await self._get_recent_bars_extended(symbol, "1Day", 2, days=5)
                    if bars:
                        latest_bar = bars[-1]
                        current_price = latest_bar['close']
                        data_source = f"daily_bars"
                        logger.info(f"📊 Using daily bars for {symbol}: ${current_price:.4f}")
                except Exception as e:
                    logger.debug(f"❌ Daily bars fallback failed for {symbol}: {e}")
            
            # FINAL VALIDATION
            if not current_price:
                raise MarketDataException(f"Unable to fetch current price for {symbol} from any source")
            
            # CACHE THE RESULT with minimal expiry for real-time accuracy
            self._cache_price(cache_key, current_price)
            
            # Enhanced logging with age information and market context
            age_info = f" (age: {price_age_seconds:.0f}s)" if price_age_seconds is not None else ""
            
            # Check if this is likely market close data vs real extended hours
            if price_age_seconds and price_age_seconds > 14400:  # Over 4 hours old
                age_hours = price_age_seconds / 3600
                
                # Convert timestamp to ET to check if it's market close
                import pytz
                et = pytz.timezone('US/Eastern')
                
                # Check if current price timestamp suggests market close
                if 'timestamp' in locals() and hasattr(best_candidate, 'timestamp'):
                    price_et = best_candidate['timestamp'].astimezone(et)
                    if price_et.hour == 15 and price_et.minute == 59:  # 3:59 PM ET
                        market_context = " ⚠️ [MARKET CLOSE DATA - NO EXTENDED HOURS]"
                    elif price_et.hour == 16 and price_et.minute == 0:  # 4:00 PM ET
                        market_context = " ⚠️ [MARKET CLOSE DATA - NO EXTENDED HOURS]"
                    else:
                        market_context = " [EXTENDED HOURS DATA UNAVAILABLE IN PAPER TRADING]"
                else:
                    market_context = " [EXTENDED HOURS DATA UNAVAILABLE IN PAPER TRADING]"
                    
                logger.warning(f"⚠️ Price data for {symbol} is {age_hours:.1f} hours old{market_context}")
            else:
                market_context = ""
            
            logger.info(f"💰 PRICE FETCHED: {symbol} = ${current_price:.4f} (source: {data_source}){age_info}{market_context}")
            
            return current_price
            
        except MarketDataException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching price for {symbol}: {str(e)}")
            raise MarketDataException(f"Failed to fetch price for {symbol}: {str(e)}")
    
    def _get_cached_price(self, cache_key: str) -> Optional[float]:
        """Get price from cache if not expired."""
        if cache_key in self._price_cache:
            cached_data = self._price_cache[cache_key]
            if datetime.utcnow() - cached_data['timestamp'] < self._cache_duration:
                return cached_data['price']
        return None
    
    def _cache_price(self, cache_key: str, price: float) -> None:
        """Cache price with timestamp."""
        self._price_cache[cache_key] = {
            'price': price,
            'timestamp': datetime.utcnow()
        }
    
    async def get_historical_data(self, symbol: str, timeframe: str, 
                                count: int) -> List[Dict[str, Any]]:
        """
        Get historical market data.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe (e.g., '1Min', '1Hour', '1Day')
            count: Number of bars to retrieve
            
        Returns:
            List of historical bars
            
        Raises:
            MarketDataException: If historical data is unavailable
        """
        try:
            logger.debug(f"Getting historical data for {symbol}: {timeframe}, {count} bars")
            
            # Convert timeframe to Alpaca TimeFrame
            alpaca_timeframe = self._convert_timeframe(timeframe)
            
            # Calculate start time based on timeframe and count
            start_time = self._calculate_start_time(timeframe, count)
            
            # Create request
            request = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=alpaca_timeframe,
                start=start_time,
                limit=count
            )
            
            # Execute request
            bars = await self._execute_bars_request(request)
            
            # Convert to standard format
            historical_data = []
            for bar in bars:
                historical_data.append({
                    'timestamp': bar.timestamp,
                    'open': float(bar.open),
                    'high': float(bar.high),
                    'low': float(bar.low),
                    'close': float(bar.close),
                    'volume': int(bar.volume)
                })
            
            logger.debug(f"Retrieved {len(historical_data)} bars for {symbol}")
            return historical_data
            
        except Exception as e:
            logger.error(f"Failed to get historical data for {symbol}: {str(e)}")
            raise MarketDataException(f"Failed to get historical data: {str(e)}")
    
    async def _get_recent_bars(self, symbol: str, timeframe: str, count: int) -> List[Dict]:
        """Get recent bars for current price calculation."""
        try:
            alpaca_timeframe = self._convert_timeframe(timeframe)
            
            # Start with last hour, but extend if market is closed
            start_time = datetime.utcnow() - timedelta(hours=1)
            
            request = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=alpaca_timeframe,
                start=start_time,
                limit=count
            )
            
            bars = await self._execute_bars_request(request)
            
            # If no bars found and it's a short timeframe, try extending the period
            if not bars and timeframe.lower() in ['1min', '5min']:
                logger.debug(f"No recent {timeframe} bars found, extending lookback period")
                
                # Try last 24 hours for minute data
                start_time = datetime.utcnow() - timedelta(hours=24)
                request.start = start_time
                bars = await self._execute_bars_request(request)
            
            if bars:
                logger.debug(f"Retrieved {len(bars)} {timeframe} bars for {symbol}")
            
            return [{
                'timestamp': bar.timestamp,
                'open': float(bar.open),
                'high': float(bar.high),
                'low': float(bar.low),
                'close': float(bar.close),
                'volume': int(bar.volume)
            } for bar in bars]
            
        except Exception as e:
            logger.error(f"Failed to get recent bars for {symbol}: {str(e)}")
            return []
    
    async def _get_recent_bars_extended(self, symbol: str, timeframe: str, count: int, 
                                      hours: int = None, days: int = None) -> List[Dict]:
        """Get recent bars with extended lookback period for current price calculation."""
        try:
            alpaca_timeframe = self._convert_timeframe(timeframe)
            
            # Calculate start time based on provided parameters
            from datetime import datetime, timedelta, timezone
            now_utc = datetime.now(timezone.utc)
            
            if days:
                start_time = now_utc - timedelta(days=days)
            elif hours:
                start_time = now_utc - timedelta(hours=hours)
            else:
                start_time = now_utc - timedelta(hours=1)  # Default to 1 hour
            
            request = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=alpaca_timeframe,
                start=start_time,
                limit=count
            )
            
            bars = await self._execute_bars_request(request)
            
            if bars:
                # Sort bars by timestamp to ensure we get the absolute latest
                bars.sort(key=lambda x: x.timestamp)
                logger.debug(f"Retrieved {len(bars)} {timeframe} bars for {symbol} from extended lookback")
                if bars:
                    latest_bar_age = now_utc.replace(tzinfo=None) - bars[-1].timestamp.replace(tzinfo=None)
                    logger.debug(f"Latest bar for {symbol}: {bars[-1].timestamp} (Age: {latest_bar_age.total_seconds()/60:.1f}m)")
            
            return [{
                'timestamp': bar.timestamp,
                'open': float(bar.open),
                'high': float(bar.high),
                'low': float(bar.low),
                'close': float(bar.close),
                'volume': int(bar.volume)
            } for bar in bars]
            
        except Exception as e:
            logger.error(f"Failed to get extended recent bars for {symbol}: {str(e)}")
            return []
    
    async def _execute_bars_request(self, request):
        """Execute bars request asynchronously."""
        try:
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, self._client.get_stock_bars, request)
            
            # Extract bars for the symbol
            symbol = request.symbol_or_symbols[0] if request.symbol_or_symbols else "unknown"
            
            # Handle different response types from alpaca-py versions
            if response:
                # Try to access the symbol data
                try:
                    # New alpaca-py format (BarSet object with data attribute)
                    if hasattr(response, 'data') and response.data:
                        if symbol in response.data:
                            bars = response.data[symbol]
                            logger.debug(f"Successfully retrieved {len(bars)} bars for {symbol} (BarSet.data format)")
                            return bars
                        else:
                            logger.debug(f"Symbol {symbol} not found in response.data: {list(response.data.keys()) if hasattr(response.data, 'keys') else 'no keys'}")
                    
                    # Alternative: Try accessing data attribute directly
                    elif hasattr(response, 'data') and hasattr(response.data, symbol):
                        bars = getattr(response.data, symbol)
                        logger.debug(f"Successfully retrieved {len(bars)} bars for {symbol} (data.symbol format)")
                        return bars
                    
                    # Old format (dict-like)
                    elif hasattr(response, '__getitem__') and symbol in response:
                        bars = response[symbol]
                        logger.debug(f"Successfully retrieved {len(bars)} bars for {symbol} (dict format)")
                        return bars
                    
                    # Try direct symbol access
                    elif hasattr(response, symbol):
                        bars = getattr(response, symbol)
                        logger.debug(f"Successfully retrieved {len(bars)} bars for {symbol} (attribute format)")
                        return bars
                    
                    else:
                        # Log available attributes for debugging
                        available_attrs = [attr for attr in dir(response) if not attr.startswith('_')]
                        logger.debug(f"No data for {symbol}. Available response attributes: {available_attrs}")
                        
                        # Try to inspect data attribute more deeply
                        if hasattr(response, 'data'):
                            data_attrs = [attr for attr in dir(response.data) if not attr.startswith('_')]
                            logger.debug(f"Available data attributes: {data_attrs}")
                            
                            # Try different ways to access the data
                            if hasattr(response.data, '__iter__'):
                                try:
                                    data_items = list(response.data)
                                    logger.debug(f"Data items: {data_items}")
                                except:
                                    pass
                        
                        return []
                        
                except Exception as access_error:
                    logger.warning(f"Error accessing {symbol} data: {access_error}")
                    return []
            else:
                logger.warning(f"No response received for {symbol}")
                return []
                
        except Exception as e:
            symbol = request.symbol_or_symbols[0] if request.symbol_or_symbols else "unknown"
            logger.error(f"Failed to execute bars request for {symbol}: {str(e)}", exc_info=True)
            return []
    
    def _convert_timeframe(self, timeframe: str) -> TimeFrame:
        """Convert timeframe string to Alpaca TimeFrame."""
        timeframe_mapping = {
            '1Min': TimeFrame.Minute,
            '1min': TimeFrame.Minute,
            '5Min': TimeFrame(5, TimeFrame.Minute.unit),
            '5min': TimeFrame(5, TimeFrame.Minute.unit),
            '15Min': TimeFrame(15, TimeFrame.Minute.unit),
            '15min': TimeFrame(15, TimeFrame.Minute.unit),
            '30Min': TimeFrame(30, TimeFrame.Minute.unit),
            '30min': TimeFrame(30, TimeFrame.Minute.unit),
            '1Hour': TimeFrame.Hour,
            '1hour': TimeFrame.Hour,
            '1h': TimeFrame.Hour,
            '4Hour': TimeFrame(4, TimeFrame.Hour.unit),
            '4hour': TimeFrame(4, TimeFrame.Hour.unit),
            '4h': TimeFrame(4, TimeFrame.Hour.unit),
            '1Day': TimeFrame.Day,
            '1day': TimeFrame.Day,
            '1d': TimeFrame.Day,
            '1Week': TimeFrame.Week,
            '1week': TimeFrame.Week,
            '1w': TimeFrame.Week,
        }
        
        return timeframe_mapping.get(timeframe, TimeFrame.Minute)
    
    def _calculate_start_time(self, timeframe: str, count: int) -> datetime:
        """Calculate start time based on timeframe and count."""
        now = datetime.utcnow()
        
        if timeframe.lower() in ['1min', '1minute']:
            return now - timedelta(minutes=count * 2)  # Buffer for weekends
        elif timeframe.lower() in ['5min', '5minute']:
            return now - timedelta(minutes=count * 10)
        elif timeframe.lower() in ['15min', '15minute']:
            return now - timedelta(minutes=count * 30)
        elif timeframe.lower() in ['30min', '30minute']:
            return now - timedelta(hours=count)
        elif timeframe.lower() in ['1h', '1hour']:
            return now - timedelta(hours=count * 2)
        elif timeframe.lower() in ['4h', '4hour']:
            return now - timedelta(hours=count * 8)
        elif timeframe.lower() in ['1d', '1day']:
            return now - timedelta(days=count * 2)
        elif timeframe.lower() in ['1w', '1week']:
            return now - timedelta(weeks=count * 2)
        else:
            return now - timedelta(hours=count)  # Default
    
    def _is_cached_price_valid(self, symbol: str) -> bool:
        """Check if cached price is still valid."""
        if symbol not in self._price_cache:
            return False
        
        cache_time = self._price_cache[symbol]['timestamp']
        return datetime.utcnow() - cache_time < self._cache_duration
    
    def clear_cache(self) -> None:
        """Clear price cache."""
        self._price_cache.clear()
        logger.debug("Price cache cleared")
    
    async def get_market_status(self, symbol: str) -> Dict[str, Any]:
        """
        Get symbol information and availability.
        Simply checks if we can get recent price data for the symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dictionary with symbol status information
        """
        try:
            # Try to get recent data to verify symbol exists
            bars = await self._get_recent_bars_extended(symbol, "1Day", 5, days=30)
            symbol_exists = len(bars) > 0
            
            last_price = None
            last_update = None
            if bars:
                last_bar = bars[-1]
                last_price = last_bar['close']
                last_update = last_bar['timestamp']
            
            return {
                'symbol': symbol,
                'symbol_exists': symbol_exists,
                'last_price': last_price,
                'last_update': last_update,
                'cache_valid': self._is_cached_price_valid(symbol)
            }
            
        except Exception as e:
            logger.error(f"Failed to get market status for {symbol}: {e}")
            return {
                'symbol': symbol,
                'symbol_exists': False,
                'last_price': None,
                'last_update': None,
                'cache_valid': False,
                'error': str(e)
            }
    
    async def _get_latest_quote_price(self, symbol: str) -> Optional[float]:
        """
        Get the latest quote price using enhanced method from sample file.
        This provides better extended hours data handling.
        """
        try:
            from alpaca.data.requests import StockLatestQuoteRequest
            
            # Create request for latest quote
            request = StockLatestQuoteRequest(symbol_or_symbols=[symbol])
            
            # Execute request
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, self._client.get_stock_latest_quote, request)
            
            if response:
                logger.debug(f"Enhanced quote response type: {type(response)}")
                
                # Handle dict response (common format)
                if isinstance(response, dict) and symbol in response:
                    quote = response[symbol]
                    logger.debug(f"Enhanced quote found: {quote}")
                    
                    # Check quote timestamp freshness (critical for after-hours)
                    quote_timestamp = getattr(quote, 'timestamp', None)
                    if quote_timestamp:
                        from datetime import datetime, timedelta
                        now = datetime.utcnow()
                        if hasattr(quote_timestamp, 'replace'):
                            quote_time = quote_timestamp.replace(tzinfo=None)
                        else:
                            quote_time = quote_timestamp
                        
                        quote_age = now - quote_time
                        
                        # More lenient during after-hours: reject only if older than 8 hours
                        max_age_hours = 8
                        if quote_age > timedelta(hours=max_age_hours):
                            logger.debug(f"Enhanced quote for {symbol} is {quote_age.total_seconds()/3600:.1f}h old - too stale")
                            return None
                        else:
                            logger.debug(f"Enhanced quote for {symbol} is {quote_age.total_seconds()/3600:.1f}h old - acceptable")
                    
                    # Enhanced bid/ask handling for extended hours
                    if hasattr(quote, 'bid_price') and hasattr(quote, 'ask_price'):
                        bid_price = float(quote.bid_price) if quote.bid_price else 0
                        ask_price = float(quote.ask_price) if quote.ask_price else 0
                        
                        # During market hours, prefer bid/ask spread
                        if bid_price > 0 and ask_price > 0:
                            price = (bid_price + ask_price) / 2
                            logger.debug(f"Enhanced quote for {symbol}: bid=${bid_price}, ask=${ask_price}, mid=${price:.2f}")
                            return price
                        # After hours: use bid if ask is 0 (common in after-hours)
                        elif bid_price > 0 and ask_price == 0:
                            logger.debug(f"After-hours enhanced quote for {symbol}: bid=${bid_price} (no ask)")
                            return bid_price
                        # Less common: use ask if bid is 0
                        elif ask_price > 0 and bid_price == 0:
                            logger.debug(f"After-hours enhanced quote for {symbol}: ask=${ask_price} (no bid)")
                            return ask_price
                        else:
                            logger.debug(f"Enhanced quote for {symbol} has no valid bid/ask: bid={bid_price}, ask={ask_price}")
                            return None
                            
                # Try alternative response format
                elif hasattr(response, symbol):
                    quote = getattr(response, symbol)
                    if hasattr(quote, 'bid_price') and hasattr(quote, 'ask_price'):
                        bid_price = float(quote.bid_price) if quote.bid_price else 0
                        ask_price = float(quote.ask_price) if quote.ask_price else 0
                        if bid_price > 0 and ask_price > 0:
                            return (bid_price + ask_price) / 2
                        elif bid_price > 0:
                            return bid_price
                        elif ask_price > 0:
                            return ask_price
            
            return None
            
        except Exception as e:
            logger.debug(f"Enhanced quote method failed for {symbol}: {e}")
            return None
    
    async def _get_latest_trade_price(self, symbol: str) -> Optional[float]:
        """
        Get the latest trade price using enhanced method from sample file.
        This is useful for after-hours when quotes might be stale but trades are current.
        """
        try:
            from alpaca.data.requests import StockLatestTradeRequest
            
            request = StockLatestTradeRequest(symbol_or_symbols=symbol)
            
            # Execute request
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, self._client.get_stock_latest_trade, request)
            
            if response and isinstance(response, dict) and symbol in response:
                trade = response[symbol]
                if hasattr(trade, 'price') and trade.price:
                    price = float(trade.price)
                    
                    # Check trade timestamp
                    if hasattr(trade, 'timestamp'):
                        from datetime import datetime, timedelta
                        import pytz
                        
                        now_utc = datetime.now(pytz.UTC)
                        trade_time = trade.timestamp
                        if hasattr(trade_time, 'tzinfo') and trade_time.tzinfo is None:
                            trade_time = pytz.UTC.localize(trade_time)
                        
                        trade_age = now_utc - trade_time
                        
                        # Allow trades up to 8 hours old for after-hours scenarios
                        if trade_age.total_seconds() <= 8 * 3600:  # 8 hours
                            logger.debug(f"Enhanced trade for {symbol}: ${price:.2f} at {trade_time} ({trade_age.total_seconds()/60:.1f}m ago)")
                            return price
                        else:
                            logger.debug(f"Enhanced trade for {symbol} is too old: {trade_age.total_seconds()/3600:.1f}h")
                            return None
            
            return None
            
        except Exception as e:
            logger.debug(f"Enhanced trade method failed for {symbol}: {e}")
            return None
    
    async def _get_recent_bars_extended(self, symbol: str, timeframe: str, count: int, 
                                      hours: int = None, days: int = None) -> List[Dict]:
        """Get recent bars with extended lookback period for current price calculation."""
        try:
            alpaca_timeframe = self._convert_timeframe(timeframe)
            
            # Calculate start time based on provided parameters
            from datetime import datetime, timedelta, timezone
            now_utc = datetime.now(timezone.utc)
            
            if days:
                start_time = now_utc - timedelta(days=days)
            elif hours:
                start_time = now_utc - timedelta(hours=hours)
            else:
                start_time = now_utc - timedelta(hours=1)  # Default to 1 hour
            
            from alpaca.data.requests import StockBarsRequest
            request = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=alpaca_timeframe,
                start=start_time,
                limit=count
            )
            
            bars = await self._execute_bars_request(request)
            
            if bars:
                # Sort bars by timestamp to ensure we get the absolute latest
                bars.sort(key=lambda x: x.timestamp)
                logger.debug(f"Retrieved {len(bars)} {timeframe} bars for {symbol} from extended lookback")
                if bars:
                    latest_bar_age = now_utc.replace(tzinfo=None) - bars[-1].timestamp.replace(tzinfo=None)
                    logger.debug(f"Latest bar for {symbol}: {bars[-1].timestamp} (Age: {latest_bar_age.total_seconds()/60:.1f}m)")
            
            return [{
                'timestamp': bar.timestamp,
                'open': float(bar.open),
                'high': float(bar.high),
                'low': float(bar.low),
                'close': float(bar.close),
                'volume': int(bar.volume)
            } for bar in bars]
            
        except Exception as e:
            logger.error(f"Failed to get extended recent bars for {symbol}: {str(e)}")
            return []
