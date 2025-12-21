"""
Unit tests for TastytradeMarketDataProvider.

Tests the Tastytrade market data provider's ability to fetch current prices
and handle both regular and extended hours trading data.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
import pytz

from src.broker.tastytrade_broker.market_data_provider import TastytradeMarketDataProvider
from src.exceptions import MarketDataException


class TestTastytradeMarketDataProvider:
    """Test suite for TastytradeMarketDataProvider."""
    
    @pytest.fixture
    def mock_session_manager(self):
        """Create a mock session manager."""
        manager = MagicMock()
        manager.get_session = AsyncMock(return_value=MagicMock())
        return manager
    
    @pytest.fixture
    def provider(self, mock_session_manager):
        """Create a provider instance for testing."""
        return TastytradeMarketDataProvider(
            session_manager=mock_session_manager,
            cache_duration_seconds=30,
            use_streaming=False
        )
    
    # =========================================================================
    # Initialization Tests
    # =========================================================================
    
    def test_initialization(self, mock_session_manager):
        """Test provider initializes correctly."""
        provider = TastytradeMarketDataProvider(
            session_manager=mock_session_manager,
            cache_duration_seconds=60,
            use_streaming=True
        )
        
        assert provider._session_manager == mock_session_manager
        assert provider._cache_duration == timedelta(seconds=60)
        assert provider._use_streaming is True
        assert provider._price_cache == {}
        assert provider._streaming_quotes == {}
    
    def test_initialization_defaults(self, mock_session_manager):
        """Test provider uses correct defaults."""
        provider = TastytradeMarketDataProvider(
            session_manager=mock_session_manager
        )
        
        assert provider._cache_duration == timedelta(seconds=30)
        assert provider._use_streaming is False
    
    # =========================================================================
    # Start/Stop Tests
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_start_without_streaming(self, provider):
        """Test start works when streaming is disabled."""
        await provider.start()
        # Should complete without error
        assert provider._streamer is None
    
    @pytest.mark.asyncio
    async def test_stop_clears_caches(self, provider):
        """Test stop clears all caches."""
        # Add some cache data
        provider._price_cache['price_AAPL'] = {
            'price': 150.0,
            'timestamp': datetime.now(timezone.utc),
            'source': 'api'
        }
        provider._streaming_quotes['AAPL'] = MagicMock()
        provider._subscribed_symbols.add('AAPL')
        
        await provider.stop()
        
        assert provider._price_cache == {}
        assert provider._streaming_quotes == {}
        assert provider._subscribed_symbols == set()
    
    # =========================================================================
    # Price Fetching Tests
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_get_current_price_uses_cache(self, provider):
        """Test that cached prices are used when fresh."""
        # Set up cache
        provider._price_cache['price_AAPL'] = {
            'price': 150.0,
            'timestamp': datetime.now(timezone.utc),
            'source': 'api'
        }
        
        price = await provider.get_current_price('AAPL')
        
        assert price == 150.0
    
    @pytest.mark.asyncio
    async def test_get_current_price_cache_expired(self, provider, mock_session_manager):
        """Test that expired cache triggers API call."""
        # Set up expired cache
        provider._price_cache['price_AAPL'] = {
            'price': 150.0,
            'timestamp': datetime.now(timezone.utc) - timedelta(minutes=5),
            'source': 'api'
        }
        
        # Mock the API call
        mock_market_data = MagicMock()
        mock_market_data.mark = 155.0
        mock_market_data.updated_at = datetime.now(timezone.utc)
        
        with patch('src.broker.tastytrade_broker.market_data_provider.get_market_data', return_value=mock_market_data):
            with patch('src.broker.tastytrade_broker.market_data_provider.run_blocking', new_callable=AsyncMock) as mock_run:
                mock_run.return_value = mock_market_data
                
                price = await provider.get_current_price('AAPL')
                
                assert price == 155.0
                # Verify new price was cached
                assert provider._price_cache['price_AAPL']['price'] == 155.0
    
    @pytest.mark.asyncio
    async def test_get_current_price_no_data_raises(self, provider, mock_session_manager):
        """Test that missing data raises MarketDataException."""
        with patch('src.broker.tastytrade_broker.market_data_provider.run_blocking', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = None
            
            with pytest.raises(MarketDataException) as exc_info:
                await provider.get_current_price('INVALID')
            
            assert "Unable to fetch price" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_current_price_uses_bid_ask_mid(self, provider, mock_session_manager):
        """Test price calculation from bid/ask."""
        mock_market_data = MagicMock()
        mock_market_data.mark = None
        mock_market_data.bid = 100.0
        mock_market_data.ask = 102.0
        mock_market_data.updated_at = datetime.now(timezone.utc)
        
        with patch('src.broker.tastytrade_broker.market_data_provider.run_blocking', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_market_data
            
            price = await provider.get_current_price('TEST')
            
            assert price == 101.0  # Mid-point of bid/ask
    
    @pytest.mark.asyncio
    async def test_get_current_price_fallback_to_close(self, provider, mock_session_manager):
        """Test fallback to close price when other prices unavailable."""
        mock_market_data = MagicMock()
        mock_market_data.mark = None
        mock_market_data.bid = None
        mock_market_data.ask = None
        mock_market_data.last = None
        mock_market_data.close = 99.50
        mock_market_data.updated_at = datetime.now(timezone.utc)
        
        with patch('src.broker.tastytrade_broker.market_data_provider.run_blocking', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_market_data
            
            price = await provider.get_current_price('TEST')
            
            assert price == 99.50
    
    # =========================================================================
    # Historical Data Tests
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_get_historical_data_returns_empty(self, provider):
        """Test that historical data returns empty list with warning."""
        result = await provider.get_historical_data('AAPL', '1Day', 10)
        
        assert result == []
    
    # =========================================================================
    # Quote Extraction Tests
    # =========================================================================
    
    def test_extract_price_from_quote_mid(self, provider):
        """Test extracting mid-price from quote."""
        quote = MagicMock()
        quote.bid_price = 100.0
        quote.ask_price = 102.0
        
        price = provider._extract_price_from_quote(quote)
        
        assert price == 101.0
    
    def test_extract_price_from_quote_ask_only(self, provider):
        """Test extracting price when only ask available."""
        quote = MagicMock()
        quote.bid_price = 0
        quote.ask_price = 102.0
        
        price = provider._extract_price_from_quote(quote)
        
        assert price == 102.0
    
    def test_extract_price_from_quote_bid_only(self, provider):
        """Test extracting price when only bid available."""
        quote = MagicMock()
        quote.bid_price = 100.0
        quote.ask_price = 0
        
        price = provider._extract_price_from_quote(quote)
        
        assert price == 100.0
    
    def test_extract_price_from_quote_none(self, provider):
        """Test extracting price when quote is None."""
        price = provider._extract_price_from_quote(None)
        assert price is None
    
    # =========================================================================
    # Market Status Tests
    # =========================================================================
    
    def test_market_status_regular_hours(self, provider):
        """Test market status detection during regular hours."""
        # Mock time to be during regular hours (10 AM ET on a weekday)
        ny_tz = pytz.timezone('America/New_York')
        mock_time = datetime(2025, 11, 24, 10, 0, 0, tzinfo=ny_tz)  # Monday 10 AM
        
        with patch('src.broker.tastytrade_broker.market_data_provider.datetime') as mock_dt:
            mock_dt.now.return_value = mock_time
            
            status = provider._get_market_status()
            
            assert status['status'] == 'REGULAR_HOURS'
            assert status['is_regular_hours'] is True
            assert status['is_extended_hours'] is False
    
    def test_market_status_pre_market(self, provider):
        """Test market status detection during pre-market."""
        ny_tz = pytz.timezone('America/New_York')
        mock_time = datetime(2025, 11, 24, 6, 0, 0, tzinfo=ny_tz)  # Monday 6 AM
        
        with patch('src.broker.tastytrade_broker.market_data_provider.datetime') as mock_dt:
            mock_dt.now.return_value = mock_time
            
            status = provider._get_market_status()
            
            assert status['status'] == 'PRE_MARKET'
            assert status['is_pre_market'] is True
            assert status['is_extended_hours'] is True
    
    def test_market_status_post_market(self, provider):
        """Test market status detection during post-market."""
        ny_tz = pytz.timezone('America/New_York')
        mock_time = datetime(2025, 11, 24, 17, 0, 0, tzinfo=ny_tz)  # Monday 5 PM
        
        with patch('src.broker.tastytrade_broker.market_data_provider.datetime') as mock_dt:
            mock_dt.now.return_value = mock_time
            
            status = provider._get_market_status()
            
            assert status['status'] == 'POST_MARKET'
            assert status['is_post_market'] is True
            assert status['is_extended_hours'] is True
    
    def test_market_status_weekend(self, provider):
        """Test market status detection on weekend."""
        ny_tz = pytz.timezone('America/New_York')
        mock_time = datetime(2025, 11, 22, 10, 0, 0, tzinfo=ny_tz)  # Saturday 10 AM
        
        with patch('src.broker.tastytrade_broker.market_data_provider.datetime') as mock_dt:
            mock_dt.now.return_value = mock_time
            
            status = provider._get_market_status()
            
            assert status['status'] == 'CLOSED'
            assert status['is_weekend'] is True
            assert status['is_closed'] is True
    
    # =========================================================================
    # Staleness Warning Tests
    # =========================================================================
    
    def test_staleness_warning_fresh_data(self, provider):
        """Test no warning for fresh data."""
        market_status = {
            'status': 'REGULAR_HOURS',
            'is_regular_hours': True,
            'is_extended_hours': False,
            'is_closed': False
        }
        
        warning = provider._get_staleness_warning(5, market_status)
        
        assert "✅" in warning
    
    def test_staleness_warning_stale_market_hours(self, provider):
        """Test warning for stale data during market hours."""
        market_status = {
            'status': 'REGULAR_HOURS',
            'is_regular_hours': True,
            'is_extended_hours': False,
            'is_closed': False
        }
        
        warning = provider._get_staleness_warning(600, market_status)  # 10 minutes
        
        assert "STALE" in warning
    
    def test_staleness_warning_extended_hours(self, provider):
        """Test warning for extended hours data."""
        market_status = {
            'status': 'PRE_MARKET',
            'is_regular_hours': False,
            'is_extended_hours': True,
            'is_closed': False
        }
        
        warning = provider._get_staleness_warning(120, market_status)  # 2 minutes
        
        assert "extended hours" in warning or "✅" in warning
    
    # =========================================================================
    # Caching Tests
    # =========================================================================
    
    def test_cache_price(self, provider):
        """Test caching a price."""
        provider._cache_price('AAPL', 150.0, 'api')
        
        assert 'price_AAPL' in provider._price_cache
        assert provider._price_cache['price_AAPL']['price'] == 150.0
        assert provider._price_cache['price_AAPL']['source'] == 'api'
    
    def test_get_cached_price_valid(self, provider):
        """Test getting a valid cached price."""
        provider._price_cache['price_AAPL'] = {
            'price': 150.0,
            'timestamp': datetime.now(timezone.utc),
            'source': 'api'
        }
        
        price = provider._get_cached_price('AAPL')
        
        assert price == 150.0
    
    def test_get_cached_price_expired(self, provider):
        """Test getting an expired cached price returns None."""
        provider._price_cache['price_AAPL'] = {
            'price': 150.0,
            'timestamp': datetime.now(timezone.utc) - timedelta(minutes=5),
            'source': 'api'
        }
        
        price = provider._get_cached_price('AAPL')
        
        assert price is None
    
    def test_get_cached_price_missing(self, provider):
        """Test getting a non-existent cached price returns None."""
        price = provider._get_cached_price('MISSING')
        
        assert price is None


class TestTastytradeMarketDataProviderStreaming:
    """Test suite for streaming functionality."""
    
    @pytest.fixture
    def mock_session_manager(self):
        """Create a mock session manager."""
        manager = MagicMock()
        manager.get_session = AsyncMock(return_value=MagicMock())
        return manager
    
    @pytest.fixture
    def streaming_provider(self, mock_session_manager):
        """Create a streaming-enabled provider."""
        return TastytradeMarketDataProvider(
            session_manager=mock_session_manager,
            cache_duration_seconds=30,
            use_streaming=True
        )
    
    @pytest.mark.asyncio
    async def test_subscribe_adds_symbols(self, streaming_provider):
        """Test subscribing adds symbols to tracking."""
        # Mock the streamer
        mock_streamer = AsyncMock()
        streaming_provider._streamer = mock_streamer
        streaming_provider._use_streaming = True
        
        await streaming_provider.subscribe(['AAPL', 'MSFT'])
        
        mock_streamer.subscribe.assert_called_once()
        assert 'AAPL' in streaming_provider._subscribed_symbols
        assert 'MSFT' in streaming_provider._subscribed_symbols
    
    @pytest.mark.asyncio
    async def test_unsubscribe_removes_symbols(self, streaming_provider):
        """Test unsubscribing removes symbols from tracking."""
        mock_streamer = AsyncMock()
        streaming_provider._streamer = mock_streamer
        streaming_provider._subscribed_symbols = {'AAPL', 'MSFT'}
        streaming_provider._streaming_quotes = {'AAPL': MagicMock()}
        
        await streaming_provider.unsubscribe(['AAPL'])
        
        mock_streamer.unsubscribe.assert_called_once()
        assert 'AAPL' not in streaming_provider._subscribed_symbols
        assert 'AAPL' not in streaming_provider._streaming_quotes
        assert 'MSFT' in streaming_provider._subscribed_symbols
    
    @pytest.mark.asyncio
    async def test_get_price_uses_streaming_quote(self, streaming_provider):
        """Test that streaming quotes are used when available."""
        mock_quote = MagicMock()
        mock_quote.bid_price = 150.0
        mock_quote.ask_price = 151.0
        
        streaming_provider._streaming_quotes['AAPL'] = mock_quote
        
        price = await streaming_provider.get_current_price('AAPL')
        
        assert price == 150.5  # Mid-point


class TestTastytradeMarketDataProviderIntegration:
    """
    Integration tests for TastytradeMarketDataProvider.
    
    These tests require actual Tastytrade credentials and are skipped
    in CI/CD environments. Run with pytest -m integration to include.
    """
    
    @pytest.mark.skip(reason="Requires live Tastytrade credentials")
    @pytest.mark.asyncio
    async def test_live_price_fetch(self):
        """Test fetching a live price from Tastytrade."""
        # This would require actual credentials
        pass
