"""
DCA Order Preview Domain Service.

Pure domain logic for generating DCA order previews matching the frontend
implementation exactly. This service calculates:
- Order ladder with target prices and deviations
- Unit quantities based on asset class and strategy
- Running average price after each fill
- Configuration validation with suggested fixes

Unit Convention (CRITICAL):
- Crypto/Forex LONG: Input amounts are in quote currency (USD/USDT)
- Crypto/Forex SHORT: Input amounts are in base units (BTC, ETH, etc.)
- Stocks/ETF LONG: Input amounts are in USD
- Stocks/ETF SHORT: Input amounts are in shares (whole numbers only)

This matches the frontend logic in dca-form-components.tsx exactly.

Author: Trading Bot Team
Version: 1.0.0
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import List, Optional, Dict, Any


# =============================================================================
# Enums
# =============================================================================

class AssetClass(str, Enum):
    """Asset class determines unit handling and rounding rules."""
    CRYPTO = "crypto"
    FOREX = "forex"
    STOCK = "stock"
    ETF = "etf"
    COMMODITY = "commodity"
    INDEX = "index"
    
    @property
    def requires_whole_units(self) -> bool:
        """Whether this asset class requires whole units (no fractions)."""
        return self in (AssetClass.STOCK, AssetClass.ETF)


class Strategy(str, Enum):
    """Trading strategy direction."""
    LONG = "long"
    SHORT = "short"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class OrderPreviewRow:
    """
    Single order in the DCA order preview ladder.
    
    Attributes:
        order_number: 0 for base order, 1+ for safety orders
        order_label: Display label (e.g., "Base Order", "SO 1")
        amount: Original configured amount (input currency/units)
        adjusted_amount: Actual amount after rounding (for whole shares)
        units: Number of units/shares for this order
        target_price: Expected fill price for this order
        price_deviation_pct: Deviation from current price (%)
        cumulative_amount: Running total of invested amount (quote currency)
        cumulative_units: Running total of acquired units
        average_price: Average entry price after this order fills
        is_invalid: True if this order would have negative/invalid price
        was_adjusted: True if amount was adjusted for whole shares
        has_insufficient_shares: True if order rounds to 0 shares
    """
    order_number: int
    order_label: str
    amount: Decimal
    adjusted_amount: Decimal
    units: Decimal
    target_price: Decimal
    price_deviation_pct: Decimal
    cumulative_amount: Decimal
    cumulative_units: Decimal
    average_price: Decimal
    is_invalid: bool = False
    was_adjusted: bool = False
    has_insufficient_shares: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "orderNumber": self.order_number,
            "orderLabel": self.order_label,
            "amount": float(self.amount),
            "adjustedAmount": float(self.adjusted_amount),
            "units": float(self.units),
            "targetPrice": float(self.target_price),
            "priceDeviationPct": float(self.price_deviation_pct),
            "cumulativeAmount": float(self.cumulative_amount),
            "cumulativeUnits": float(self.cumulative_units),
            "averagePrice": float(self.average_price),
            "isInvalid": self.is_invalid,
            "wasAdjusted": self.was_adjusted,
            "hasInsufficientShares": self.has_insufficient_shares,
        }


@dataclass
class ValidationIssue:
    """
    Validation issue detected in DCA configuration.
    
    Attributes:
        code: Machine-readable issue code
        message: Human-readable description
        severity: "error" or "warning"
        affected_order: Order number where issue occurs (if applicable)
    """
    code: str
    message: str
    severity: str  # "error" | "warning"
    affected_order: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "affectedOrder": self.affected_order,
        }


@dataclass
class SuggestedFix:
    """
    Suggested fix for an invalid DCA configuration.
    
    Attributes:
        orders_count: Suggested new order count
        step_percent: Suggested new step percent (if changed)
        description: Human-readable description of the fix
    """
    orders_count: int
    step_percent: Optional[Decimal] = None
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "ordersCount": self.orders_count,
            "stepPercent": float(self.step_percent) if self.step_percent else None,
            "description": self.description,
        }


@dataclass
class DCAOrderPreviewResult:
    """
    Complete result of DCA order preview calculation.
    
    Attributes:
        orders: List of all orders in the ladder
        total_investment: Total quote currency investment
        total_units: Total units/shares acquired
        final_average_price: Average entry price after all orders
        max_deviation_pct: Maximum price deviation from current price
        is_valid: Whether configuration is valid
        issues: List of validation issues
        suggested_fix: Suggested fix if configuration is invalid
    """
    orders: List[OrderPreviewRow]
    total_investment: Decimal
    total_units: Decimal
    final_average_price: Decimal
    max_deviation_pct: Decimal
    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    suggested_fix: Optional[SuggestedFix] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "orders": [o.to_dict() for o in self.orders],
            "totals": {
                "totalInvestment": float(self.total_investment),
                "totalUnits": float(self.total_units),
                "finalAveragePrice": float(self.final_average_price),
                "maxDeviationPct": float(self.max_deviation_pct),
            },
            "validation": {
                "isValid": self.is_valid,
                "issues": [i.to_dict() for i in self.issues],
                "suggestedFix": self.suggested_fix.to_dict() if self.suggested_fix else None,
            },
        }


@dataclass
class DCAOrderPreviewRequest:
    """
    Request parameters for DCA order preview calculation.
    
    All amount fields follow the unit convention based on asset_class and strategy:
    - Crypto/Forex LONG: base_order_amount and averaging_orders_amount are in USD
    - Crypto/Forex SHORT: base_order_amount and averaging_orders_amount are in base units
    - Stocks/ETF LONG: base_order_amount and averaging_orders_amount are in USD
    - Stocks/ETF SHORT: base_order_amount and averaging_orders_amount are in shares
    """
    # Asset info
    symbol: str
    asset_class: AssetClass
    strategy: Strategy
    current_price: Decimal
    
    # Base order
    base_order_amount: Decimal
    
    # Averaging orders (safety orders)
    averaging_orders_amount: Decimal
    orders_count: int
    step_percent: Decimal
    amount_multiplier: Decimal = Decimal("1.0")
    amount_multiplier_enabled: bool = False
    step_multiplier: Decimal = Decimal("1.0")
    step_multiplier_enabled: bool = False


# =============================================================================
# DCA Order Preview Service
# =============================================================================

class DCAOrderPreviewService:
    """
    Domain service for calculating DCA order previews.
    
    This service generates order ladders matching the frontend implementation
    exactly, including:
    - Target prices based on step percent and multiplier
    - Order sizing with amount multiplier
    - Running average price calculation
    - Whole share rounding for stocks/ETFs
    - Configuration validation with suggested fixes
    
    Usage:
        service = DCAOrderPreviewService()
        result = service.calculate(DCAOrderPreviewRequest(...))
    """
    
    # Rounding precision for different calculations
    PRICE_PRECISION = Decimal("0.01")  # 2 decimal places for prices/amounts
    UNIT_PRECISION = Decimal("0.0001")  # 4 decimal places for units
    
    def calculate(self, request: DCAOrderPreviewRequest) -> DCAOrderPreviewResult:
        """
        Calculate complete DCA order preview.
        
        Args:
            request: DCA order preview request parameters
            
        Returns:
            Complete preview result with orders, totals, and validation
        """
        # Validate inputs
        if request.current_price <= 0 or request.orders_count < 1:
            return DCAOrderPreviewResult(
                orders=[],
                total_investment=Decimal("0"),
                total_units=Decimal("0"),
                final_average_price=Decimal("0"),
                max_deviation_pct=Decimal("0"),
                is_valid=False,
                issues=[ValidationIssue(
                    code="INVALID_INPUT",
                    message="Current price must be positive and orders count must be at least 1",
                    severity="error",
                )],
            )
        
        # Calculate orders
        orders = self._calculate_orders(request)
        
        # Validate configuration
        issues, suggested_fix = self._validate_configuration(request, orders)
        
        # Calculate totals (only for valid orders)
        valid_orders = [o for o in orders if not o.is_invalid]
        
        # For calculating total investment, we need to consider input type
        # Short positions: input is units, so use adjusted_amount (quote value)
        # Long positions: input is quote, so use amount (but adjusted for stocks)
        requires_whole_units = request.asset_class.requires_whole_units
        input_is_units = request.strategy == Strategy.SHORT
        
        if requires_whole_units or input_is_units:
            total_investment = sum(o.adjusted_amount for o in valid_orders)
        else:
            total_investment = sum(o.amount for o in valid_orders)
        
        total_units = sum(o.units for o in valid_orders)
        
        last_valid = valid_orders[-1] if valid_orders else None
        final_avg_price = last_valid.average_price if last_valid else Decimal("0")
        max_deviation = last_valid.price_deviation_pct if last_valid else Decimal("0")
        
        is_valid = len(issues) == 0 or all(i.severity == "warning" for i in issues)
        
        return DCAOrderPreviewResult(
            orders=orders,
            total_investment=total_investment.quantize(self.PRICE_PRECISION),
            total_units=total_units.quantize(self.UNIT_PRECISION),
            final_average_price=final_avg_price,
            max_deviation_pct=max_deviation,
            is_valid=is_valid,
            issues=issues,
            suggested_fix=suggested_fix,
        )
    
    def _calculate_orders(self, req: DCAOrderPreviewRequest) -> List[OrderPreviewRow]:
        """
        Calculate all orders in the DCA ladder.
        
        Matches frontend calculateDCAOrders() function exactly.
        """
        orders: List[OrderPreviewRow] = []
        
        requires_whole_units = req.asset_class.requires_whole_units
        is_short = req.strategy == Strategy.SHORT
        
        # Effective multipliers
        eff_amount_mult = req.amount_multiplier if req.amount_multiplier_enabled else Decimal("1.0")
        eff_step_mult = req.step_multiplier if req.step_multiplier_enabled else Decimal("1.0")
        
        # Calculate weighted sum for distributing averaging orders amount
        # amounts are: base_amt, base_amt*mult, base_amt*mult^2, ...
        total_weight = sum(
            eff_amount_mult ** i for i in range(req.orders_count)
        )
        
        first_avg_order_amount = (
            req.averaging_orders_amount / total_weight 
            if total_weight > 0 
            else req.averaging_orders_amount / req.orders_count
        )
        
        # Track cumulative values
        cumulative_amount = Decimal("0")
        cumulative_units = Decimal("0")
        current_step_pct = req.step_percent
        current_deviation = Decimal("0")
        
        # Unit convention:
        # Short: input is units (shares for stocks, coins for crypto)
        # Long: input is quote currency (USD)
        input_is_units = is_short
        
        # =====================================================================
        # Base Order (Order #0)
        # =====================================================================
        base_units, adjusted_base_amount, base_was_adjusted, base_insufficient = (
            self._calculate_order_units(
                amount=req.base_order_amount,
                price=req.current_price,
                input_is_units=input_is_units,
                requires_whole_units=requires_whole_units,
            )
        )
        
        cumulative_amount = adjusted_base_amount
        cumulative_units = base_units
        
        orders.append(OrderPreviewRow(
            order_number=0,
            order_label="Base Order",
            amount=req.base_order_amount.quantize(self.PRICE_PRECISION),
            adjusted_amount=adjusted_base_amount.quantize(self.PRICE_PRECISION),
            units=base_units.quantize(self.UNIT_PRECISION),
            target_price=req.current_price.quantize(self.PRICE_PRECISION),
            price_deviation_pct=Decimal("0"),
            cumulative_amount=cumulative_amount.quantize(self.PRICE_PRECISION),
            cumulative_units=cumulative_units.quantize(self.UNIT_PRECISION),
            average_price=req.current_price.quantize(self.PRICE_PRECISION),
            is_invalid=False,
            was_adjusted=base_was_adjusted,
            has_insufficient_shares=base_insufficient,
        ))
        
        # =====================================================================
        # Averaging Orders (Safety Orders)
        # =====================================================================
        current_order_amount = first_avg_order_amount
        
        for i in range(req.orders_count):
            # Calculate deviation for this order (geometric series)
            if i == 0:
                current_deviation = req.step_percent
            else:
                current_deviation += current_step_pct
                if req.step_multiplier_enabled:
                    current_step_pct *= eff_step_mult
            
            # Check if deviation would result in invalid price (long only)
            is_invalid = not is_short and current_deviation >= Decimal("100")
            
            # Calculate target price
            # Long: price goes DOWN (1 - deviation/100)
            # Short: price goes UP (1 + deviation/100)
            if is_short:
                price_multiplier = Decimal("1") + current_deviation / Decimal("100")
            else:
                price_multiplier = Decimal("1") - current_deviation / Decimal("100")
            
            target_price = max(Decimal("0"), req.current_price * price_multiplier)
            
            # Calculate units for this order
            if is_invalid:
                units = Decimal("0")
                adjusted_amount = Decimal("0")
                was_adjusted = False
                has_insufficient = False
            else:
                units, adjusted_amount, was_adjusted, has_insufficient = (
                    self._calculate_order_units(
                        amount=current_order_amount,
                        price=target_price,
                        input_is_units=input_is_units,
                        requires_whole_units=requires_whole_units,
                    )
                )
            
            # Update cumulative values
            cumulative_amount += adjusted_amount
            cumulative_units += units
            
            # Calculate average price
            avg_price = (
                cumulative_amount / cumulative_units 
                if cumulative_units > 0 
                else Decimal("0")
            )
            
            orders.append(OrderPreviewRow(
                order_number=i + 1,
                order_label=f"SO {i + 1}",
                amount=current_order_amount.quantize(self.PRICE_PRECISION),
                adjusted_amount=adjusted_amount.quantize(self.PRICE_PRECISION),
                units=units.quantize(self.UNIT_PRECISION),
                target_price=target_price.quantize(self.PRICE_PRECISION),
                price_deviation_pct=current_deviation.quantize(self.PRICE_PRECISION),
                cumulative_amount=cumulative_amount.quantize(self.PRICE_PRECISION),
                cumulative_units=cumulative_units.quantize(self.UNIT_PRECISION),
                average_price=avg_price.quantize(self.PRICE_PRECISION),
                is_invalid=is_invalid,
                was_adjusted=was_adjusted,
                has_insufficient_shares=has_insufficient,
            ))
            
            # Apply amount multiplier for next order
            if req.amount_multiplier_enabled:
                current_order_amount *= eff_amount_mult
        
        return orders
    
    def _calculate_order_units(
        self,
        amount: Decimal,
        price: Decimal,
        input_is_units: bool,
        requires_whole_units: bool,
    ) -> tuple[Decimal, Decimal, bool, bool]:
        """
        Calculate units and adjusted amount for an order.
        
        Args:
            amount: Configured amount (units or quote currency based on input_is_units)
            price: Target price for the order
            input_is_units: True if amount is in units, False if in quote currency
            requires_whole_units: True for stocks/ETFs that need whole shares
            
        Returns:
            Tuple of (units, adjusted_amount, was_adjusted, has_insufficient_shares)
        """
        if price <= 0:
            return Decimal("0"), Decimal("0"), False, False
        
        was_adjusted = False
        has_insufficient = False
        
        if input_is_units:
            # Short positions: input is units (shares/coins)
            raw_units = amount
            if requires_whole_units:
                # Round to whole shares
                units = Decimal(round(float(raw_units)))
                if units < 1 and raw_units > 0:
                    has_insufficient = True
                    units = Decimal("0")
                was_adjusted = units != raw_units
            else:
                # Crypto/forex: keep fractional
                units = raw_units
            adjusted_amount = units * price
        elif requires_whole_units:
            # Long stocks: input is USD, calculate shares
            raw_units = amount / price
            units = Decimal(round(float(raw_units)))
            if units < 1 and raw_units > 0:
                has_insufficient = True
                units = Decimal("0")
            adjusted_amount = units * price
            was_adjusted = units != raw_units
        else:
            # Long crypto/forex: input is USD, calculate units (keep fractional)
            units = amount / price
            adjusted_amount = amount
        
        return units, adjusted_amount, was_adjusted, has_insufficient
    
    def _validate_configuration(
        self,
        req: DCAOrderPreviewRequest,
        orders: List[OrderPreviewRow],
    ) -> tuple[List[ValidationIssue], Optional[SuggestedFix]]:
        """
        Validate DCA configuration and generate suggested fixes.
        
        Checks for:
        1. Negative/zero prices (long positions with >100% deviation)
        2. Insufficient shares (orders rounding to 0)
        3. Over-allocation (total shares exceed budget for short stocks)
        """
        issues: List[ValidationIssue] = []
        suggested_fix: Optional[SuggestedFix] = None
        
        requires_whole_units = req.asset_class.requires_whole_units
        is_short = req.strategy == Strategy.SHORT
        input_is_shares = requires_whole_units and is_short
        
        # Check for invalid orders (negative prices)
        invalid_orders = [o for o in orders if o.is_invalid]
        if invalid_orders:
            first_invalid = invalid_orders[0]
            issues.append(ValidationIssue(
                code="NEGATIVE_PRICE",
                message=(
                    f"Order {first_invalid.order_number} would have a price deviation of "
                    f"{first_invalid.price_deviation_pct}% which results in a negative price. "
                    "Maximum allowed deviation is 100%."
                ),
                severity="error",
                affected_order=first_invalid.order_number,
            ))
            
            # Find max valid orders count
            valid_count = len([o for o in orders if not o.is_invalid]) - 1  # Exclude base order
            if valid_count > 0:
                suggested_fix = SuggestedFix(
                    orders_count=valid_count,
                    step_percent=req.step_percent,
                    description=f"Reduce to {valid_count} safety orders",
                )
        
        # Check for insufficient shares
        insufficient_orders = [o for o in orders if o.has_insufficient_shares]
        if insufficient_orders and not invalid_orders:
            first_insufficient = insufficient_orders[0]
            if len(insufficient_orders) == 1:
                msg = f"{first_insufficient.order_label} would have 0 shares."
            else:
                labels = ", ".join(o.order_label for o in insufficient_orders)
                msg = f"{len(insufficient_orders)} orders would have 0 shares ({labels})."
            
            issues.append(ValidationIssue(
                code="INSUFFICIENT_SHARES",
                message=msg + " Increase the total shares or reduce the number of orders.",
                severity="error",
                affected_order=first_insufficient.order_number,
            ))
            
            # Find max orders with at least 1 share
            valid_safety_orders = [
                o for o in orders 
                if o.units >= 1 and o.order_number > 0
            ]
            if valid_safety_orders:
                suggested_fix = SuggestedFix(
                    orders_count=len(valid_safety_orders),
                    step_percent=req.step_percent,
                    description=f"Reduce to {len(valid_safety_orders)} safety orders",
                )
        
        # Check for over-allocation (short stocks only)
        if input_is_shares and not invalid_orders and not insufficient_orders:
            configured_total = req.base_order_amount + req.averaging_orders_amount
            actual_total = sum(o.units for o in orders)
            
            if actual_total > configured_total:
                over_amount = actual_total - configured_total
                issues.append(ValidationIssue(
                    code="OVER_ALLOCATION",
                    message=(
                        f"Rounding to whole shares results in {int(actual_total)} shares, "
                        f"but only {int(configured_total)} shares are configured "
                        f"({int(over_amount)} over budget). "
                        "Reduce the number of orders or increase the total shares."
                    ),
                    severity="error",
                ))
                
                # Find max orders that fit within budget
                max_orders = self._find_max_orders_within_budget(req)
                if max_orders > 0:
                    suggested_fix = SuggestedFix(
                        orders_count=max_orders,
                        step_percent=req.step_percent,
                        description=f"Reduce to {max_orders} safety orders",
                    )
        
        # Check for adjusted orders (warning only)
        adjusted_orders = [
            o for o in orders 
            if o.was_adjusted and not o.has_insufficient_shares
        ]
        if adjusted_orders and requires_whole_units:
            issues.append(ValidationIssue(
                code="SHARES_ADJUSTED",
                message=(
                    "Stock orders adjusted to whole shares. "
                    "Actual investment amounts may differ from configured values."
                ),
                severity="warning",
            ))
        
        return issues, suggested_fix
    
    def _find_max_orders_within_budget(self, req: DCAOrderPreviewRequest) -> int:
        """
        Find maximum number of safety orders that fit within share budget.
        
        Used for short stock positions where rounding may exceed configured shares.
        """
        eff_amount_mult = req.amount_multiplier if req.amount_multiplier_enabled else Decimal("1.0")
        configured_total = req.base_order_amount + req.averaging_orders_amount
        
        for try_count in range(req.orders_count - 1, 0, -1):
            # Calculate weights for this order count
            total_weight = sum(eff_amount_mult ** i for i in range(try_count))
            first_order_shares = (
                req.averaging_orders_amount / total_weight 
                if total_weight > 0 
                else req.averaging_orders_amount / try_count
            )
            
            # Calculate total shares with rounding
            total_shares = Decimal(round(float(req.base_order_amount)))  # Base order
            current_shares = first_order_shares
            for i in range(try_count):
                total_shares += Decimal(round(float(current_shares)))
                if req.amount_multiplier_enabled:
                    current_shares *= eff_amount_mult
            
            if total_shares <= configured_total:
                return try_count
        
        return 0


# =============================================================================
# Convenience Functions
# =============================================================================

def calculate_dca_preview(
    symbol: str,
    asset_class: str,
    strategy: str,
    current_price: float,
    base_order_amount: float,
    averaging_orders_amount: float,
    orders_count: int,
    step_percent: float,
    amount_multiplier: float = 1.0,
    amount_multiplier_enabled: bool = False,
    step_multiplier: float = 1.0,
    step_multiplier_enabled: bool = False,
) -> Dict[str, Any]:
    """
    Convenience function to calculate DCA preview with simple types.
    
    Args:
        symbol: Trading symbol (e.g., "AAPL", "BTC/USD")
        asset_class: Asset class ("crypto", "stock", "forex", "etf")
        strategy: Strategy direction ("long" or "short")
        current_price: Current market price
        base_order_amount: Base order amount (USD for long, units for short)
        averaging_orders_amount: Total averaging orders amount
        orders_count: Number of safety orders
        step_percent: Price step between orders (e.g., 1.5 for 1.5%)
        amount_multiplier: Multiplier for order sizing
        amount_multiplier_enabled: Whether to apply amount multiplier
        step_multiplier: Multiplier for step sizes
        step_multiplier_enabled: Whether to apply step multiplier
        
    Returns:
        Dictionary with orders, totals, and validation info
    """
    service = DCAOrderPreviewService()
    
    request = DCAOrderPreviewRequest(
        symbol=symbol,
        asset_class=AssetClass(asset_class),
        strategy=Strategy(strategy),
        current_price=Decimal(str(current_price)),
        base_order_amount=Decimal(str(base_order_amount)),
        averaging_orders_amount=Decimal(str(averaging_orders_amount)),
        orders_count=orders_count,
        step_percent=Decimal(str(step_percent)),
        amount_multiplier=Decimal(str(amount_multiplier)),
        amount_multiplier_enabled=amount_multiplier_enabled,
        step_multiplier=Decimal(str(step_multiplier)),
        step_multiplier_enabled=step_multiplier_enabled,
    )
    
    result = service.calculate(request)
    return result.to_dict()
