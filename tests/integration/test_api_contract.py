"""
API Contract Tests - Frontend/Backend Type Alignment.

These tests ensure that the domain models, API responses, and frontend
TypeScript types remain aligned. Any breaking changes to the API shape
will cause these tests to fail.

Run with: pytest tests/integration/test_api_contract.py -v

Author: Trading Bot Team
Version: 1.0.0
"""

import json
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Set

from src.domain.bot_enums import (
    BotState,
    BotType,
    BotOperationalPhase,
    BotAction,
    BotOrderType,
    PositionMode,
    MarginMode,
)
from src.domain.bot_config import BotConfiguration, DCAConfig
from src.domain.bot_state import Bot, BotPerformance, BotOrder


# =============================================================================
# Expected API Contract Definitions
# =============================================================================
# These define the exact shape that the frontend TypeScript types expect.
# If these change, the frontend api-types.ts must be updated accordingly.

EXPECTED_BOT_STATE_VALUES = {
    "created", "starting", "running", "paused", 
    "stopping", "stopped", "completed", "error"
}

EXPECTED_BOT_TYPE_VALUES = {
    "dca", "combo", "grid", "futures_dca", "futures_combo", "spot_loop"
}

EXPECTED_BOT_OPERATIONAL_PHASE_VALUES = {
    "waiting_for_signal", "signal_matched", "entering_position",
    "in_position", "averaging_down", "taking_profit", "stopping_loss",
    "closing_position", "position_closed", "price_in_range",
    "price_out_of_range", "rebalancing", "waiting_for_webhook",
    "webhook_received", "in_cooldown", "cooldown_expired", "idle"
}

EXPECTED_BOT_ACTION_VALUES = {
    "start", "stop", "pause", "resume", "modify",
    "manual_average", "adjust_margin", "close_position",
    "view_details", "delete"
}

# Bot.to_dict() expected fields (matches frontend Bot interface)
EXPECTED_BOT_FIELDS = {
    # Core identity
    "id": str,
    "userId": str,
    "name": str,
    "description": (str, type(None)),
    "symbol": str,
    "exchange": str,
    
    # Type and state
    "botType": str,
    "botTypeDisplay": str,
    "state": str,
    "isActive": bool,
    "errorMessage": (str, type(None)),
    
    # Nested objects
    "configuration": dict,
    "performance": dict,
    
    # Timestamps (ISO 8601 strings)
    "createdAt": str,
    "startedAt": (str, type(None)),
    "stoppedAt": (str, type(None)),
    "lastActivityAt": (str, type(None)),
    
    # Display fields
    "tradingTimeDisplay": str,
    "tags": list,
    "availableActions": list,
    
    # Operational phase tracking
    "operationalPhase": str,
    "lastSignalMatchAt": (str, type(None)),
    "signalIndicatorsStatus": (dict, type(None)),
    
    # Price range tracking
    "priceRangeStatus": (str, type(None)),
    "gridLowerBound": (str, type(None)),
    "gridUpperBound": (str, type(None)),
    
    # Cooldown tracking
    "cooldownUntil": (str, type(None)),
    "lastOrderAt": (str, type(None)),
    
    # Deal tracking
    "currentDealId": (str, type(None)),
    "completedDeals": int,
}

# BotPerformance.to_dict() expected fields
EXPECTED_PERFORMANCE_FIELDS = {
    "totalInvested": str,
    "currentValue": str,
    "totalPnL": str,
    "totalPnLPercent": str,
    "botProfit": str,
    "botProfitPercent": str,
    "positionPnL": str,
    "positionPnLPercent": str,
    "avgDailyProfit": str,
    "avgDailyProfitPercent": str,
    "positionSize": str,
    "avgEntryPrice": str,
    "currentPrice": str,
    "dcaLayersUsed": int,
    "pendingOrdersCount": int,
    "pendingOrdersValue": str,
    "totalTrades": int,
    "winningTrades": int,
    "losingTrades": int,
    "winRate": str,
    "tradingTimeSeconds": int,
}

# BotOrder.to_dict() expected fields
EXPECTED_ORDER_FIELDS = {
    "id": str,
    "botId": str,
    "orderType": str,
    "side": str,
    "quantity": str,
    "price": (str, type(None)),
    "filledQuantity": str,
    "filledPrice": (str, type(None)),
    "status": str,
    "createdAt": str,
    "filledAt": (str, type(None)),
}


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_dca_config() -> DCAConfig:
    """Create a sample DCA configuration for testing."""
    # DCAConfig uses nested configs - use defaults
    return DCAConfig()


@pytest.fixture
def sample_bot_config(sample_dca_config: DCAConfig) -> BotConfiguration:
    """Create a sample bot configuration for testing."""
    return BotConfiguration(
        symbol="BTC/USDT",
        exchange="binance",
        leverage=1,
        margin_mode=MarginMode.ISOLATED,
        dca_config=sample_dca_config,
    )


@pytest.fixture
def sample_performance() -> BotPerformance:
    """Create a sample performance object for testing."""
    return BotPerformance()


@pytest.fixture
def sample_bot(sample_bot_config: BotConfiguration, sample_performance: BotPerformance) -> Bot:
    """Create a fully populated sample bot for testing."""
    bot = Bot(
        id="bot-123",
        user_id="user-456",
        name="Test DCA Bot",
        description="A test bot for contract validation",
        configuration=sample_bot_config,
        state=BotState.RUNNING,
        error_message=None,
        tags=["test", "dca"],
    )
    bot.performance = sample_performance
    bot.operational_phase = BotOperationalPhase.IN_POSITION
    # Use naive datetime to match trading_time_display property
    bot.started_at = datetime.utcnow()
    bot.completed_deals = 5
    return bot


@pytest.fixture
def sample_order() -> BotOrder:
    """Create a sample order for testing."""
    return BotOrder(
        id="order-789",
        bot_id="bot-123",
        order_type="limit",
        side="buy",
        quantity=Decimal("0.1"),
        price=Decimal("50000"),
        filled_quantity=Decimal("0.05"),
        filled_price=Decimal("49900"),
        status="partial",
    )


# =============================================================================
# Enum Contract Tests
# =============================================================================

class TestEnumContracts:
    """Test that Python enum values match expected frontend values."""
    
    def test_bot_state_values_match_frontend(self):
        """BotState enum values must match frontend BotState type."""
        actual_values = {state.value for state in BotState}
        assert actual_values == EXPECTED_BOT_STATE_VALUES, (
            f"BotState enum values changed! "
            f"Missing: {EXPECTED_BOT_STATE_VALUES - actual_values}, "
            f"Extra: {actual_values - EXPECTED_BOT_STATE_VALUES}. "
            f"Update trading-terminal/lib/types/api-types.ts if intentional."
        )
    
    def test_bot_type_values_match_frontend(self):
        """BotType enum values must match frontend BotType type."""
        actual_values = {bt.value for bt in BotType}
        assert actual_values == EXPECTED_BOT_TYPE_VALUES, (
            f"BotType enum values changed! "
            f"Missing: {EXPECTED_BOT_TYPE_VALUES - actual_values}, "
            f"Extra: {actual_values - EXPECTED_BOT_TYPE_VALUES}. "
            f"Update trading-terminal/lib/types/api-types.ts if intentional."
        )
    
    def test_bot_operational_phase_values_match_frontend(self):
        """BotOperationalPhase enum values must match frontend type."""
        actual_values = {phase.value for phase in BotOperationalPhase}
        assert actual_values == EXPECTED_BOT_OPERATIONAL_PHASE_VALUES, (
            f"BotOperationalPhase enum values changed! "
            f"Missing: {EXPECTED_BOT_OPERATIONAL_PHASE_VALUES - actual_values}, "
            f"Extra: {actual_values - EXPECTED_BOT_OPERATIONAL_PHASE_VALUES}. "
            f"Update trading-terminal/lib/types/api-types.ts if intentional."
        )
    
    def test_bot_action_values_match_frontend(self):
        """BotAction enum values must match frontend BotAction type."""
        actual_values = {action.value for action in BotAction}
        assert actual_values == EXPECTED_BOT_ACTION_VALUES, (
            f"BotAction enum values changed! "
            f"Missing: {EXPECTED_BOT_ACTION_VALUES - actual_values}, "
            f"Extra: {actual_values - EXPECTED_BOT_ACTION_VALUES}. "
            f"Update trading-terminal/lib/types/api-types.ts if intentional."
        )


# =============================================================================
# Bot Model Contract Tests
# =============================================================================

class TestBotModelContract:
    """Test that Bot.to_dict() matches the frontend Bot interface."""
    
    def test_bot_to_dict_has_all_expected_fields(self, sample_bot: Bot):
        """Bot.to_dict() must contain all fields expected by frontend."""
        result = sample_bot.to_dict()
        
        missing_fields = set(EXPECTED_BOT_FIELDS.keys()) - set(result.keys())
        assert not missing_fields, (
            f"Bot.to_dict() is missing fields: {missing_fields}. "
            f"Frontend Bot interface expects these fields."
        )
    
    def test_bot_to_dict_field_types(self, sample_bot: Bot):
        """Bot.to_dict() field types must match frontend expectations."""
        result = sample_bot.to_dict()
        
        for field_name, expected_type in EXPECTED_BOT_FIELDS.items():
            assert field_name in result, f"Missing field: {field_name}"
            actual_value = result[field_name]
            
            # Handle union types (e.g., str | None)
            if isinstance(expected_type, tuple):
                assert isinstance(actual_value, expected_type), (
                    f"Field '{field_name}' has wrong type. "
                    f"Expected {expected_type}, got {type(actual_value).__name__}"
                )
            else:
                assert isinstance(actual_value, expected_type), (
                    f"Field '{field_name}' has wrong type. "
                    f"Expected {expected_type.__name__}, got {type(actual_value).__name__}"
                )
    
    def test_bot_state_value_is_valid(self, sample_bot: Bot):
        """Bot state value must be a valid frontend BotState."""
        result = sample_bot.to_dict()
        assert result["state"] in EXPECTED_BOT_STATE_VALUES, (
            f"Invalid state value: {result['state']}. "
            f"Must be one of: {EXPECTED_BOT_STATE_VALUES}"
        )
    
    def test_bot_type_value_is_valid(self, sample_bot: Bot):
        """Bot type value must be a valid frontend BotType."""
        result = sample_bot.to_dict()
        assert result["botType"] in EXPECTED_BOT_TYPE_VALUES, (
            f"Invalid botType value: {result['botType']}. "
            f"Must be one of: {EXPECTED_BOT_TYPE_VALUES}"
        )
    
    def test_operational_phase_value_is_valid(self, sample_bot: Bot):
        """Operational phase value must be valid."""
        result = sample_bot.to_dict()
        assert result["operationalPhase"] in EXPECTED_BOT_OPERATIONAL_PHASE_VALUES, (
            f"Invalid operationalPhase value: {result['operationalPhase']}. "
            f"Must be one of: {EXPECTED_BOT_OPERATIONAL_PHASE_VALUES}"
        )
    
    def test_available_actions_are_valid(self, sample_bot: Bot):
        """Available actions must all be valid BotAction values."""
        result = sample_bot.to_dict()
        invalid_actions = set(result["availableActions"]) - EXPECTED_BOT_ACTION_VALUES
        assert not invalid_actions, (
            f"Invalid action values: {invalid_actions}. "
            f"Must be one of: {EXPECTED_BOT_ACTION_VALUES}"
        )
    
    def test_bot_to_dict_is_json_serializable(self, sample_bot: Bot):
        """Bot.to_dict() must be JSON serializable for API responses."""
        result = sample_bot.to_dict()
        try:
            json_str = json.dumps(result)
            assert json_str  # Non-empty
        except (TypeError, ValueError) as e:
            pytest.fail(f"Bot.to_dict() is not JSON serializable: {e}")
    
    def test_timestamps_are_iso_format(self, sample_bot: Bot):
        """Timestamp fields must be ISO 8601 formatted strings."""
        result = sample_bot.to_dict()
        
        timestamp_fields = ["createdAt", "startedAt", "stoppedAt", "lastActivityAt"]
        for field in timestamp_fields:
            value = result.get(field)
            if value is not None:
                # Verify it's parseable as ISO 8601
                try:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    pytest.fail(f"Field '{field}' is not ISO 8601 format: {value}")


# =============================================================================
# Performance Model Contract Tests
# =============================================================================

class TestPerformanceModelContract:
    """Test that BotPerformance.to_dict() matches frontend expectations."""
    
    def test_performance_has_all_expected_fields(self, sample_performance: BotPerformance):
        """BotPerformance.to_dict() must contain all expected fields."""
        result = sample_performance.to_dict()
        
        missing_fields = set(EXPECTED_PERFORMANCE_FIELDS.keys()) - set(result.keys())
        assert not missing_fields, (
            f"BotPerformance.to_dict() is missing fields: {missing_fields}. "
            f"Frontend BotPerformance interface expects these fields."
        )
    
    def test_performance_field_types(self, sample_performance: BotPerformance):
        """BotPerformance.to_dict() field types must match expectations."""
        result = sample_performance.to_dict()
        
        for field_name, expected_type in EXPECTED_PERFORMANCE_FIELDS.items():
            assert field_name in result, f"Missing field: {field_name}"
            assert isinstance(result[field_name], expected_type), (
                f"Field '{field_name}' has wrong type. "
                f"Expected {expected_type.__name__}, got {type(result[field_name]).__name__}"
            )
    
    def test_decimal_fields_are_strings(self, sample_performance: BotPerformance):
        """Decimal fields must be serialized as strings for precision."""
        result = sample_performance.to_dict()
        
        decimal_fields = [
            "totalInvested", "currentValue", "totalPnL", "totalPnLPercent",
            "botProfit", "botProfitPercent", "positionPnL", "positionPnLPercent",
            "avgDailyProfit", "avgDailyProfitPercent", "positionSize",
            "avgEntryPrice", "currentPrice", "pendingOrdersValue", "winRate"
        ]
        
        for field in decimal_fields:
            assert isinstance(result[field], str), (
                f"Decimal field '{field}' should be string, got {type(result[field]).__name__}"
            )


# =============================================================================
# Order Model Contract Tests
# =============================================================================

class TestOrderModelContract:
    """Test that BotOrder.to_dict() matches frontend expectations."""
    
    def test_order_has_all_expected_fields(self, sample_order: BotOrder):
        """BotOrder.to_dict() must contain all expected fields."""
        result = sample_order.to_dict()
        
        missing_fields = set(EXPECTED_ORDER_FIELDS.keys()) - set(result.keys())
        assert not missing_fields, (
            f"BotOrder.to_dict() is missing fields: {missing_fields}. "
            f"Frontend expects these fields."
        )
    
    def test_order_field_types(self, sample_order: BotOrder):
        """BotOrder.to_dict() field types must match expectations."""
        result = sample_order.to_dict()
        
        for field_name, expected_type in EXPECTED_ORDER_FIELDS.items():
            assert field_name in result, f"Missing field: {field_name}"
            actual_value = result[field_name]
            
            if isinstance(expected_type, tuple):
                assert isinstance(actual_value, expected_type), (
                    f"Field '{field_name}' has wrong type. "
                    f"Expected {expected_type}, got {type(actual_value).__name__}"
                )
            else:
                assert isinstance(actual_value, expected_type), (
                    f"Field '{field_name}' has wrong type. "
                    f"Expected {expected_type.__name__}, got {type(actual_value).__name__}"
                )


# =============================================================================
# Cross-Layer Integration Tests
# =============================================================================

class TestCrossLayerIntegration:
    """Test integration between domain models and database layer."""
    
    def test_bot_roundtrip_through_cosmos_mappers(self, sample_bot: Bot):
        """Bot should survive roundtrip through Cosmos DB mappers."""
        from src.database.cosmos_bot_repository import (
            bot_to_cosmos_doc,
            cosmos_doc_to_bot,
        )
        
        # Convert to Cosmos document
        cosmos_doc = bot_to_cosmos_doc(sample_bot)
        
        # Verify it's a plain dict (JSON-serializable)
        assert isinstance(cosmos_doc, dict)
        json.dumps(cosmos_doc)  # Should not raise
        
        # Convert back to domain model
        restored_bot = cosmos_doc_to_bot(cosmos_doc)
        
        # Verify key properties are preserved
        assert restored_bot.id == sample_bot.id
        assert restored_bot.user_id == sample_bot.user_id
        assert restored_bot.name == sample_bot.name
        assert restored_bot.state == sample_bot.state
        assert restored_bot.configuration.symbol == sample_bot.configuration.symbol
    
    def test_all_bot_states_have_valid_api_representation(self):
        """Every BotState must serialize to a valid API value."""
        for state in BotState:
            assert state.value in EXPECTED_BOT_STATE_VALUES, (
                f"BotState.{state.name} has value '{state.value}' "
                f"which is not in the frontend contract."
            )
    
    def test_all_bot_types_have_valid_api_representation(self):
        """Every BotType must serialize to a valid API value."""
        for bot_type in BotType:
            assert bot_type.value in EXPECTED_BOT_TYPE_VALUES, (
                f"BotType.{bot_type.name} has value '{bot_type.value}' "
                f"which is not in the frontend contract."
            )


# =============================================================================
# API Response Shape Tests
# =============================================================================

class TestApiResponseShapes:
    """Test that API response shapes match frontend expectations."""
    
    def test_bot_list_response_shape(self, sample_bot: Bot):
        """Bots list API response must have expected shape."""
        # Simulate API response
        response = {
            "bots": [sample_bot.to_dict()],
            "total": 1,
            "page": 1,
            "pageSize": 10,
        }
        
        assert "bots" in response
        assert isinstance(response["bots"], list)
        assert len(response["bots"]) == 1
        
        # Verify bot shape
        bot_data = response["bots"][0]
        assert "id" in bot_data
        assert "state" in bot_data
        assert "botType" in bot_data
    
    def test_single_bot_response_shape(self, sample_bot: Bot):
        """Single bot API response must have expected shape."""
        response = sample_bot.to_dict()
        
        # Must have all required fields
        required_fields = ["id", "userId", "name", "symbol", "state", "botType"]
        for field in required_fields:
            assert field in response, f"Missing required field: {field}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
