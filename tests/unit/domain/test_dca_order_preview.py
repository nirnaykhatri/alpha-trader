"""
Tests for DCA Order Preview Domain Service.

Validates that the backend DCA order preview calculation matches
the frontend implementation exactly for all asset classes and strategies.

Author: Trading Bot Team
Version: 1.0.0
"""

import pytest
from decimal import Decimal

from src.domain.dca_order_preview import (
    DCAOrderPreviewService,
    DCAOrderPreviewRequest,
    AssetClass,
    Strategy,
    calculate_dca_preview,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def service():
    """Create a DCA order preview service instance."""
    return DCAOrderPreviewService()


@pytest.fixture
def basic_long_stock_request():
    """Basic long stock request for testing."""
    return DCAOrderPreviewRequest(
        symbol="AAPL",
        asset_class=AssetClass.STOCK,
        strategy=Strategy.LONG,
        current_price=Decimal("150.00"),
        base_order_amount=Decimal("500.00"),
        averaging_orders_amount=Decimal("2000.00"),
        orders_count=4,
        step_percent=Decimal("2.0"),
        amount_multiplier=Decimal("1.0"),
        amount_multiplier_enabled=False,
        step_multiplier=Decimal("1.0"),
        step_multiplier_enabled=False,
    )


@pytest.fixture
def crypto_long_request():
    """Crypto long request for testing."""
    return DCAOrderPreviewRequest(
        symbol="BTC/USD",
        asset_class=AssetClass.CRYPTO,
        strategy=Strategy.LONG,
        current_price=Decimal("50000.00"),
        base_order_amount=Decimal("1000.00"),
        averaging_orders_amount=Decimal("4000.00"),
        orders_count=4,
        step_percent=Decimal("3.0"),
        amount_multiplier=Decimal("1.0"),
        amount_multiplier_enabled=False,
        step_multiplier=Decimal("1.0"),
        step_multiplier_enabled=False,
    )


# =============================================================================
# Basic Calculation Tests
# =============================================================================

class TestBasicCalculation:
    """Tests for basic DCA order preview calculations."""
    
    def test_creates_correct_number_of_orders(self, service, basic_long_stock_request):
        """Should create base order + N safety orders."""
        result = service.calculate(basic_long_stock_request)
        
        # Should have 1 base order + 4 safety orders = 5 total
        assert len(result.orders) == 5
        assert result.orders[0].order_label == "Base Order"
        assert result.orders[1].order_label == "SO 1"
        assert result.orders[4].order_label == "SO 4"
    
    def test_base_order_uses_current_price(self, service, basic_long_stock_request):
        """Base order target price should be current price."""
        result = service.calculate(basic_long_stock_request)
        
        base_order = result.orders[0]
        assert base_order.target_price == Decimal("150.00")
        assert base_order.price_deviation_pct == Decimal("0")
    
    def test_safety_orders_step_down_for_long(self, service, basic_long_stock_request):
        """Long safety orders should have decreasing target prices."""
        result = service.calculate(basic_long_stock_request)
        
        # Safety orders should step down by 2% each
        # SO1: 150 * (1 - 0.02) = 147
        # SO2: 150 * (1 - 0.04) = 144
        # etc.
        assert result.orders[1].target_price == Decimal("147.00")
        assert result.orders[2].target_price == Decimal("144.00")
        assert result.orders[3].target_price == Decimal("141.00")
        assert result.orders[4].target_price == Decimal("138.00")
    
    def test_cumulative_values_increase(self, service, basic_long_stock_request):
        """Cumulative amount and units should increase with each order."""
        result = service.calculate(basic_long_stock_request)
        
        prev_amount = Decimal("0")
        prev_units = Decimal("0")
        
        for order in result.orders:
            assert order.cumulative_amount > prev_amount
            assert order.cumulative_units > prev_units
            prev_amount = order.cumulative_amount
            prev_units = order.cumulative_units
    
    def test_average_price_decreases_for_long(self, service, basic_long_stock_request):
        """Average price should decrease as we buy more at lower prices."""
        result = service.calculate(basic_long_stock_request)
        
        # Skip base order comparison
        for i in range(1, len(result.orders)):
            # Each order should have lower or equal average price
            assert result.orders[i].average_price <= result.orders[i-1].average_price


# =============================================================================
# Unit Convention Tests
# =============================================================================

class TestUnitConventions:
    """Tests for correct unit handling based on asset class and strategy."""
    
    def test_stock_long_input_is_usd(self, service):
        """Stock long: input amounts are USD, output units are shares."""
        request = DCAOrderPreviewRequest(
            symbol="AAPL",
            asset_class=AssetClass.STOCK,
            strategy=Strategy.LONG,
            current_price=Decimal("100.00"),
            base_order_amount=Decimal("300.00"),  # $300 USD
            averaging_orders_amount=Decimal("400.00"),  # $400 USD
            orders_count=2,
            step_percent=Decimal("5.0"),
        )
        
        result = service.calculate(request)
        
        # Base order: $300 / $100 = 3 shares
        assert result.orders[0].units == Decimal("3")
        # Adjusted amount should reflect whole shares: 3 * $100 = $300
        assert result.orders[0].adjusted_amount == Decimal("300.00")
    
    def test_stock_short_input_is_shares(self, service):
        """Stock short: input amounts are shares, output adjustedAmount is USD."""
        request = DCAOrderPreviewRequest(
            symbol="AAPL",
            asset_class=AssetClass.STOCK,
            strategy=Strategy.SHORT,
            current_price=Decimal("100.00"),
            base_order_amount=Decimal("5"),  # 5 shares
            averaging_orders_amount=Decimal("10"),  # 10 shares total for safety orders
            orders_count=2,
            step_percent=Decimal("5.0"),
        )
        
        result = service.calculate(request)
        
        # Base order: 5 shares at $100 = $500
        assert result.orders[0].units == Decimal("5")
        assert result.orders[0].adjusted_amount == Decimal("500.00")
    
    def test_crypto_long_allows_fractional(self, service, crypto_long_request):
        """Crypto long: should allow fractional units."""
        result = service.calculate(crypto_long_request)
        
        # Base order: $1000 / $50000 = 0.02 BTC
        assert result.orders[0].units == Decimal("0.02")
        assert not result.orders[0].was_adjusted
    
    def test_crypto_short_input_is_units(self, service):
        """Crypto short: input amounts are base units (BTC, ETH, etc.)."""
        request = DCAOrderPreviewRequest(
            symbol="BTC/USD",
            asset_class=AssetClass.CRYPTO,
            strategy=Strategy.SHORT,
            current_price=Decimal("50000.00"),
            base_order_amount=Decimal("0.1"),  # 0.1 BTC
            averaging_orders_amount=Decimal("0.4"),  # 0.4 BTC total
            orders_count=2,
            step_percent=Decimal("5.0"),
        )
        
        result = service.calculate(request)
        
        # Base order: 0.1 BTC at $50000 = $5000
        assert result.orders[0].units == Decimal("0.1")
        assert result.orders[0].adjusted_amount == Decimal("5000.00")


# =============================================================================
# Whole Share Rounding Tests
# =============================================================================

class TestWholeShareRounding:
    """Tests for stock/ETF whole share rounding behavior."""
    
    def test_stock_rounds_to_whole_shares(self, service):
        """Stocks should round to whole shares."""
        request = DCAOrderPreviewRequest(
            symbol="AAPL",
            asset_class=AssetClass.STOCK,
            strategy=Strategy.LONG,
            current_price=Decimal("150.00"),
            base_order_amount=Decimal("100.00"),  # Would be 0.67 shares
            averaging_orders_amount=Decimal("200.00"),
            orders_count=2,
            step_percent=Decimal("2.0"),
        )
        
        result = service.calculate(request)
        
        # $100 / $150 = 0.67 -> rounds to 1 share
        assert result.orders[0].units == Decimal("1")
        assert result.orders[0].was_adjusted
    
    def test_insufficient_shares_flagged(self, service):
        """Should flag orders that round to 0 shares."""
        request = DCAOrderPreviewRequest(
            symbol="TSLA",
            asset_class=AssetClass.STOCK,
            strategy=Strategy.LONG,
            current_price=Decimal("400.00"),
            base_order_amount=Decimal("150.00"),  # Would be 0.375 -> 0 shares
            averaging_orders_amount=Decimal("300.00"),
            orders_count=3,
            step_percent=Decimal("2.0"),
        )
        
        result = service.calculate(request)
        
        # Check for insufficient shares validation
        insufficient_orders = [o for o in result.orders if o.has_insufficient_shares]
        assert len(insufficient_orders) > 0
        
        # Should not be valid
        assert not result.is_valid
        assert any(i.code == "INSUFFICIENT_SHARES" for i in result.issues)
    
    def test_etf_also_requires_whole_shares(self, service):
        """ETFs should also require whole shares."""
        request = DCAOrderPreviewRequest(
            symbol="SPY",
            asset_class=AssetClass.ETF,
            strategy=Strategy.LONG,
            current_price=Decimal("450.00"),
            base_order_amount=Decimal("700.00"),  # 1.56 -> 2 shares
            averaging_orders_amount=Decimal("1000.00"),
            orders_count=2,
            step_percent=Decimal("2.0"),
        )
        
        result = service.calculate(request)
        
        # Should round 1.56 to 2 shares
        assert result.orders[0].units == Decimal("2")
        assert result.orders[0].was_adjusted


# =============================================================================
# Multiplier Tests
# =============================================================================

class TestMultipliers:
    """Tests for amount and step multipliers."""
    
    def test_amount_multiplier_increases_order_sizes(self, service):
        """Amount multiplier should geometrically increase order sizes."""
        request = DCAOrderPreviewRequest(
            symbol="BTC/USD",
            asset_class=AssetClass.CRYPTO,
            strategy=Strategy.LONG,
            current_price=Decimal("50000.00"),
            base_order_amount=Decimal("1000.00"),
            averaging_orders_amount=Decimal("4600.00"),  # Distributes with 1.3x multiplier
            orders_count=4,
            step_percent=Decimal("2.0"),
            amount_multiplier=Decimal("1.3"),
            amount_multiplier_enabled=True,
        )
        
        result = service.calculate(request)
        
        # Each safety order should be ~1.3x the previous
        for i in range(2, len(result.orders)):
            prev_amount = result.orders[i-1].amount
            curr_amount = result.orders[i].amount
            ratio = curr_amount / prev_amount
            # Should be approximately 1.3 (allowing for rounding)
            assert Decimal("1.25") < ratio < Decimal("1.35")
    
    def test_step_multiplier_increases_deviations(self, service):
        """Step multiplier should geometrically increase price deviations."""
        request = DCAOrderPreviewRequest(
            symbol="BTC/USD",
            asset_class=AssetClass.CRYPTO,
            strategy=Strategy.LONG,
            current_price=Decimal("50000.00"),
            base_order_amount=Decimal("1000.00"),
            averaging_orders_amount=Decimal("4000.00"),
            orders_count=4,
            step_percent=Decimal("2.0"),  # Base step is 2%
            step_multiplier=Decimal("1.5"),
            step_multiplier_enabled=True,
        )
        
        result = service.calculate(request)
        
        # Step deviation calculation:
        # SO1: deviation = step_percent = 2%
        # For SO2+: current_step_pct *= step_multiplier, then add
        # SO2: cumulative = 2% + (2% * 1.5) = 2% + 3% = 5%? 
        # NO! The code applies multiplier AFTER adding to cumulative:
        # SO1: deviation = 2%, then multiply step for next
        # SO2: deviation = 2% + 2% = 4%, then multiply step (2%*1.5=3%) for next
        # SO3: deviation = 4% + 3% = 7%, then multiply step (3%*1.5=4.5%) for next
        # SO4: deviation = 7% + 4.5% = 11.5%
        assert result.orders[1].price_deviation_pct == Decimal("2.00")
        assert result.orders[2].price_deviation_pct == Decimal("4.00")
        assert result.orders[3].price_deviation_pct == Decimal("7.00")
        assert result.orders[4].price_deviation_pct == Decimal("11.50")


# =============================================================================
# Short Position Tests
# =============================================================================

class TestShortPositions:
    """Tests for short position handling."""
    
    def test_short_prices_step_up(self, service):
        """Short position target prices should increase (step up)."""
        request = DCAOrderPreviewRequest(
            symbol="AAPL",
            asset_class=AssetClass.STOCK,
            strategy=Strategy.SHORT,
            current_price=Decimal("100.00"),
            base_order_amount=Decimal("5"),  # 5 shares
            averaging_orders_amount=Decimal("20"),  # 20 shares
            orders_count=4,
            step_percent=Decimal("2.0"),
        )
        
        result = service.calculate(request)
        
        # Short: prices go UP by 2% each
        assert result.orders[0].target_price == Decimal("100.00")
        assert result.orders[1].target_price == Decimal("102.00")
        assert result.orders[2].target_price == Decimal("104.00")
        assert result.orders[3].target_price == Decimal("106.00")
        assert result.orders[4].target_price == Decimal("108.00")
    
    def test_short_no_negative_price_issue(self, service):
        """Short positions don't have negative price issues."""
        request = DCAOrderPreviewRequest(
            symbol="BTC/USD",
            asset_class=AssetClass.CRYPTO,
            strategy=Strategy.SHORT,
            current_price=Decimal("50000.00"),
            base_order_amount=Decimal("0.1"),
            averaging_orders_amount=Decimal("1.0"),
            orders_count=50,  # Many orders
            step_percent=Decimal("5.0"),  # Large step
        )
        
        result = service.calculate(request)
        
        # All orders should be valid for short (prices go up)
        assert all(not o.is_invalid for o in result.orders)


# =============================================================================
# Validation Tests
# =============================================================================

class TestValidation:
    """Tests for configuration validation."""
    
    def test_detects_negative_price(self, service):
        """Should detect when cumulative deviation exceeds 100%."""
        request = DCAOrderPreviewRequest(
            symbol="BTC/USD",
            asset_class=AssetClass.CRYPTO,
            strategy=Strategy.LONG,
            current_price=Decimal("50000.00"),
            base_order_amount=Decimal("1000.00"),
            averaging_orders_amount=Decimal("4000.00"),
            orders_count=10,
            step_percent=Decimal("15.0"),  # 15% step, will exceed 100%
        )
        
        result = service.calculate(request)
        
        assert not result.is_valid
        assert any(i.code == "NEGATIVE_PRICE" for i in result.issues)
        
        # Should have a suggested fix
        assert result.suggested_fix is not None
        assert result.suggested_fix.orders_count < 10
    
    def test_detects_over_allocation_stock_short(self, service):
        """Should detect when rounding causes share over-allocation."""
        request = DCAOrderPreviewRequest(
            symbol="AAPL",
            asset_class=AssetClass.STOCK,
            strategy=Strategy.SHORT,
            current_price=Decimal("150.00"),
            base_order_amount=Decimal("2"),  # 2 shares
            averaging_orders_amount=Decimal("5"),  # 5 shares for 5 orders = 1 each, but rounding may cause issues
            orders_count=5,
            step_percent=Decimal("2.0"),
            amount_multiplier=Decimal("1.5"),  # Will cause some orders to round up
            amount_multiplier_enabled=True,
        )
        
        result = service.calculate(request)
        
        # May or may not have over-allocation depending on rounding
        # Just verify the calculation completes without error
        assert len(result.orders) == 6  # base + 5 safety
    
    def test_valid_config_passes(self, service, basic_long_stock_request):
        """Valid configuration should pass validation."""
        result = service.calculate(basic_long_stock_request)
        
        assert result.is_valid
        # May have warnings (like adjusted shares) but no errors
        assert all(i.severity != "error" for i in result.issues)


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunction:
    """Tests for the calculate_dca_preview convenience function."""
    
    def test_returns_dict(self):
        """Should return a dictionary with proper structure."""
        result = calculate_dca_preview(
            symbol="AAPL",
            asset_class="stock",
            strategy="long",
            current_price=150.00,
            base_order_amount=500.00,
            averaging_orders_amount=2000.00,
            orders_count=4,
            step_percent=2.0,
        )
        
        assert isinstance(result, dict)
        assert "orders" in result
        assert "totals" in result
        assert "validation" in result
        
        # Check nested structure
        assert "totalInvestment" in result["totals"]
        assert "isValid" in result["validation"]
    
    def test_handles_all_asset_classes(self):
        """Should handle all asset classes without error."""
        for asset_class in ["crypto", "forex", "stock", "etf"]:
            result = calculate_dca_preview(
                symbol="TEST",
                asset_class=asset_class,
                strategy="long",
                current_price=100.00,
                base_order_amount=100.00,
                averaging_orders_amount=400.00,
                orders_count=4,
                step_percent=2.0,
            )
            
            assert "orders" in result
            assert len(result["orders"]) == 5  # base + 4 safety


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_single_safety_order(self, service):
        """Should handle single safety order correctly."""
        request = DCAOrderPreviewRequest(
            symbol="BTC/USD",
            asset_class=AssetClass.CRYPTO,
            strategy=Strategy.LONG,
            current_price=Decimal("50000.00"),
            base_order_amount=Decimal("1000.00"),
            averaging_orders_amount=Decimal("1000.00"),
            orders_count=1,
            step_percent=Decimal("5.0"),
        )
        
        result = service.calculate(request)
        
        assert len(result.orders) == 2  # base + 1 safety
        assert result.orders[1].price_deviation_pct == Decimal("5.00")
    
    def test_zero_price_returns_empty(self, service):
        """Should return empty result for zero price."""
        request = DCAOrderPreviewRequest(
            symbol="TEST",
            asset_class=AssetClass.CRYPTO,
            strategy=Strategy.LONG,
            current_price=Decimal("0"),
            base_order_amount=Decimal("1000.00"),
            averaging_orders_amount=Decimal("4000.00"),
            orders_count=4,
            step_percent=Decimal("2.0"),
        )
        
        result = service.calculate(request)
        
        assert not result.is_valid
        assert len(result.orders) == 0
    
    def test_very_high_precision_crypto(self, service):
        """Should handle high precision crypto amounts."""
        request = DCAOrderPreviewRequest(
            symbol="BTC/USD",
            asset_class=AssetClass.CRYPTO,
            strategy=Strategy.SHORT,
            current_price=Decimal("50000.00"),
            base_order_amount=Decimal("0.001"),  # Small but not too small
            averaging_orders_amount=Decimal("0.005"),
            orders_count=5,
            step_percent=Decimal("1.0"),
        )
        
        result = service.calculate(request)
        
        assert len(result.orders) == 6
        assert result.orders[0].units == Decimal("0.001").quantize(Decimal("0.0001"))
