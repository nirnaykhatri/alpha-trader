"""
Reconciliation Service

Handles reconciliation between database state and broker state:
- Position verification
- External close detection
- State synchronization
- Conflict resolution

Extracted from TradingBotOrchestrator to follow Single Responsibility Principle.
This service focuses on ensuring database and broker states are consistent.

SOLID Compliance:
- SRP: Single responsibility for state reconciliation
- OCP: Extensible for new reconciliation strategies
- LSP: N/A (no inheritance hierarchy)
- ISP: Focused interface for reconciliation only
- DIP: Depends on abstractions (interfaces) not concretions

Thread Safety: Async-safe (uses async database/broker operations)

Author: Trading Bot Team
Version: 1.1.0 - Uses canonical interfaces from src.interfaces and src.broker.interfaces
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any, Protocol

from src import Position, Order
from src.interfaces import IPositionManager
from src.broker.interfaces import IBrokerAccountProvider

logger = logging.getLogger(__name__)


# ============================================================================
# Service-Specific Protocol Definitions (not duplicating canonical interfaces)
# ============================================================================

class ITradeService(Protocol):
    """
    Protocol for trade service operations specific to reconciliation.
    
    Note: This is NOT a duplicate of a canonical interface - ITradeService
    is specific to this service's needs for handling external position closes.
    """
    
    async def handle_externally_closed_position(
        self, symbol: str, position_quantity: float
    ) -> bool:
        """Handle position closed outside the bot."""
        ...


# ============================================================================
# Data Classes for Reconciliation Results
# ============================================================================

@dataclass(frozen=True)
class PositionReconciliationResult:
    """
    Result of position reconciliation.
    
    Attributes:
        symbol: Position symbol
        is_reconciled: Whether reconciliation was successful
        action_taken: Description of action taken (or None if no action needed)
        db_quantity: Database position quantity
        broker_quantity: Broker position quantity
        discrepancy: Description of any discrepancy found
    """
    symbol: str
    is_reconciled: bool
    action_taken: Optional[str]
    db_quantity: float
    broker_quantity: float
    discrepancy: Optional[str] = None


@dataclass(frozen=True)
class ReconciliationSummary:
    """
    Summary of a full reconciliation run.
    
    Attributes:
        timestamp: When reconciliation was performed
        positions_checked: Number of positions checked
        positions_reconciled: Number with discrepancies resolved
        positions_failed: Number that failed reconciliation
        errors: List of error messages
        results: Individual position results
    """
    timestamp: datetime
    positions_checked: int
    positions_reconciled: int
    positions_failed: int
    errors: List[str]
    results: List[PositionReconciliationResult]


# ============================================================================
# Reconciliation Service
# ============================================================================

class ReconciliationService:
    """
    Service for reconciling database state with broker state.
    
    This service handles:
    - Detecting positions closed externally (outside the bot)
    - Syncing database with broker reality
    - Logging discrepancies for audit trail
    - Triggering appropriate handlers for state changes
    
    The service is stateless and can be called periodically or on-demand.
    
    Usage:
        reconciliation_service = ReconciliationService(
            position_manager=position_manager,
            broker_provider=broker_provider,
            trade_service=trade_service
        )
        
        # Reconcile a specific position
        result = await reconciliation_service.reconcile_position("AAPL")
        
        # Full reconciliation run
        summary = await reconciliation_service.reconcile_all()
    """
    
    def __init__(
        self,
        position_manager: IPositionManager,
        broker_provider: IBrokerAccountProvider,
        trade_service: ITradeService,
    ):
        """
        Initialize ReconciliationService.
        
        Args:
            position_manager: Position management service
            broker_provider: Broker account provider for position verification
            trade_service: Trade service for handling closed positions
        """
        self._position_manager = position_manager
        self._broker_provider = broker_provider
        self._trade_service = trade_service
        logger.debug("ReconciliationService initialized")
    
    async def reconcile_position(self, symbol: str) -> PositionReconciliationResult:
        """
        Reconcile a single position with broker state.
        
        Args:
            symbol: Position symbol to reconcile
            
        Returns:
            PositionReconciliationResult with outcome
        """
        try:
            # Get database position
            db_position = await self._position_manager.get_position(symbol)
            db_qty = db_position.quantity if db_position else 0.0
            
            # Get broker position
            broker_qty = await self._broker_provider.get_actual_position(symbol)
            
            if broker_qty is None:
                return PositionReconciliationResult(
                    symbol=symbol,
                    is_reconciled=False,
                    action_taken=None,
                    db_quantity=db_qty,
                    broker_quantity=0.0,
                    discrepancy="Could not verify broker position"
                )
            
            # Check for discrepancy
            if abs(db_qty) > 0 and broker_qty == 0:
                # Position closed externally
                return await self._handle_external_close(
                    symbol, db_qty, broker_qty
                )
            
            if abs(broker_qty) > 0 and abs(db_qty) == 0:
                # Position exists at broker but not in database (orphan)
                return PositionReconciliationResult(
                    symbol=symbol,
                    is_reconciled=False,
                    action_taken=None,
                    db_quantity=db_qty,
                    broker_quantity=broker_qty,
                    discrepancy="Orphan position at broker (not in database)"
                )
            
            # Check direction mismatch
            if db_qty != 0 and broker_qty != 0:
                db_sign = 1 if db_qty > 0 else -1
                broker_sign = 1 if broker_qty > 0 else -1
                
                if db_sign != broker_sign:
                    db_dir = "LONG" if db_qty > 0 else "SHORT"
                    broker_dir = "LONG" if broker_qty > 0 else "SHORT"
                    return PositionReconciliationResult(
                        symbol=symbol,
                        is_reconciled=False,
                        action_taken=None,
                        db_quantity=db_qty,
                        broker_quantity=broker_qty,
                        discrepancy=f"Direction mismatch: DB={db_dir}, Broker={broker_dir}"
                    )
                
                # Check quantity mismatch (within tolerance)
                qty_diff = abs(abs(db_qty) - abs(broker_qty))
                qty_diff_pct = (qty_diff / max(abs(db_qty), abs(broker_qty))) * 100
                
                if qty_diff_pct > 5:  # 5% tolerance
                    return PositionReconciliationResult(
                        symbol=symbol,
                        is_reconciled=False,
                        action_taken=None,
                        db_quantity=db_qty,
                        broker_quantity=broker_qty,
                        discrepancy=f"Quantity mismatch: {qty_diff_pct:.1f}% difference"
                    )
            
            # Positions match
            return PositionReconciliationResult(
                symbol=symbol,
                is_reconciled=True,
                action_taken=None,
                db_quantity=db_qty,
                broker_quantity=broker_qty
            )
            
        except Exception as e:
            logger.error(f"Error reconciling position {symbol}: {e}")
            return PositionReconciliationResult(
                symbol=symbol,
                is_reconciled=False,
                action_taken=None,
                db_quantity=0.0,
                broker_quantity=0.0,
                discrepancy=f"Error: {str(e)}"
            )
    
    async def _handle_external_close(
        self,
        symbol: str,
        db_qty: float,
        broker_qty: float
    ) -> PositionReconciliationResult:
        """
        Handle a position that was closed externally.
        
        Args:
            symbol: Position symbol
            db_qty: Database quantity
            broker_qty: Broker quantity (should be 0)
            
        Returns:
            PositionReconciliationResult with outcome
        """
        logger.info(f"📋 External close detected: {symbol}")
        logger.info(f"   Database: {db_qty}")
        logger.info(f"   Broker: {broker_qty}")
        
        try:
            # Use TradeService to handle the external close
            success = await self._trade_service.handle_externally_closed_position(
                symbol=symbol,
                position_quantity=db_qty
            )
            
            if success:
                # Close position in database
                await self._position_manager.close_position(symbol)
                
                return PositionReconciliationResult(
                    symbol=symbol,
                    is_reconciled=True,
                    action_taken="Closed database position (external close)",
                    db_quantity=db_qty,
                    broker_quantity=broker_qty
                )
            else:
                return PositionReconciliationResult(
                    symbol=symbol,
                    is_reconciled=False,
                    action_taken="Attempted to handle external close",
                    db_quantity=db_qty,
                    broker_quantity=broker_qty,
                    discrepancy="TradeService failed to handle external close"
                )
                
        except Exception as e:
            logger.error(f"Error handling external close for {symbol}: {e}")
            return PositionReconciliationResult(
                symbol=symbol,
                is_reconciled=False,
                action_taken=None,
                db_quantity=db_qty,
                broker_quantity=broker_qty,
                discrepancy=f"Error handling external close: {str(e)}"
            )
    
    async def reconcile_all(self) -> ReconciliationSummary:
        """
        Perform full reconciliation of all database positions.
        
        Returns:
            ReconciliationSummary with overall results
        """
        timestamp = datetime.utcnow()
        results: List[PositionReconciliationResult] = []
        errors: List[str] = []
        
        try:
            # Get all database positions with non-zero quantity
            positions = await self._position_manager.get_all_positions()
            active_positions = [p for p in positions if p.quantity != 0]
            
            logger.info(f"🔄 Starting reconciliation for {len(active_positions)} positions")
            
            for position in active_positions:
                try:
                    result = await self.reconcile_position(position.symbol)
                    results.append(result)
                    
                    if result.discrepancy:
                        logger.warning(
                            f"⚠️ Discrepancy for {position.symbol}: {result.discrepancy}"
                        )
                    if result.action_taken:
                        logger.info(
                            f"✅ Action for {position.symbol}: {result.action_taken}"
                        )
                        
                except Exception as e:
                    error_msg = f"Error reconciling {position.symbol}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)
                    
                    results.append(PositionReconciliationResult(
                        symbol=position.symbol,
                        is_reconciled=False,
                        action_taken=None,
                        db_quantity=position.quantity,
                        broker_quantity=0.0,
                        discrepancy=error_msg
                    ))
            
            # Calculate summary
            reconciled = sum(1 for r in results if r.is_reconciled)
            failed = sum(1 for r in results if not r.is_reconciled)
            
            logger.info(
                f"🔄 Reconciliation complete: {reconciled}/{len(results)} reconciled, "
                f"{failed} with issues"
            )
            
            return ReconciliationSummary(
                timestamp=timestamp,
                positions_checked=len(results),
                positions_reconciled=reconciled,
                positions_failed=failed,
                errors=errors,
                results=results
            )
            
        except Exception as e:
            error_msg = f"Error during full reconciliation: {str(e)}"
            errors.append(error_msg)
            logger.error(error_msg)
            
            return ReconciliationSummary(
                timestamp=timestamp,
                positions_checked=len(results),
                positions_reconciled=0,
                positions_failed=len(results),
                errors=errors,
                results=results
            )
    
    async def verify_position_with_broker(
        self,
        position: Position
    ) -> tuple[bool, Optional[float], Optional[str]]:
        """
        Verify a position exists at broker with matching direction.
        
        This is a convenience method for quick position verification before
        executing trades.
        
        Args:
            position: Position to verify
            
        Returns:
            Tuple of (is_valid, broker_quantity, error_message)
        """
        try:
            broker_qty = await self._broker_provider.get_actual_position(position.symbol)
            
            if broker_qty is None:
                return False, None, "Could not verify broker position"
            
            if broker_qty == 0 and position.quantity != 0:
                return False, broker_qty, "Position closed at broker"
            
            if broker_qty != 0 and position.quantity != 0:
                db_sign = 1 if position.quantity > 0 else -1
                broker_sign = 1 if broker_qty > 0 else -1
                
                if db_sign != broker_sign:
                    return False, broker_qty, "Direction mismatch"
            
            return True, broker_qty, None
            
        except Exception as e:
            return False, None, str(e)


# ============================================================================
# Factory Function
# ============================================================================

def create_reconciliation_service(
    position_manager: IPositionManager,
    broker_provider: IBrokerAccountProvider,
    trade_service: ITradeService,
) -> ReconciliationService:
    """
    Factory function to create ReconciliationService.
    
    Args:
        position_manager: Position management service
        broker_provider: Broker account provider
        trade_service: Trade lifecycle service
        
    Returns:
        Configured ReconciliationService instance
    """
    return ReconciliationService(
        position_manager=position_manager,
        broker_provider=broker_provider,
        trade_service=trade_service,
    )
