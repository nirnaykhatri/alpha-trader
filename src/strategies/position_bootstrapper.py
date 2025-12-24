"""
Position Bootstrapper

Extracts position restoration and hydration logic from DCAStrategy
to maintain Single Responsibility Principle.
"""

import asyncio
import logging
import uuid
from typing import Dict, List, Optional
from datetime import datetime

# Import from original source to avoid circular imports
from src.strategies.position_state import PositionState, PositionDirection, TradePhase

logger = logging.getLogger(__name__)


class PositionBootstrapper:
    """
    Handles position restoration from database with DCA metadata hydration.
    
    Separates persistence concerns from strategy logic.
    
    Example:
        bootstrapper = PositionBootstrapper(position_manager, dca_metadata_manager)
        positions = await bootstrapper.restore_positions()
    """
    
    def __init__(self, position_manager, dca_metadata_manager=None):
        """
        Initialize position bootstrapper.
        
        Args:
            position_manager: Position manager instance
            dca_metadata_manager: DCA metadata manager instance (optional)
        """
        self.position_manager = position_manager
        self.dca_metadata_manager = dca_metadata_manager
        logger.info("PositionBootstrapper initialized")
    
    async def restore_positions(self) -> Dict[str, PositionState]:
        """
        Restore all active positions from database.
        
        Returns:
            Dictionary mapping symbol to PositionState
        """
        try:
            if not self.position_manager:
                logger.info("No position manager available, skipping restoration")
                return {}
            
            # Get all active positions from database
            positions = await self.position_manager.get_all_positions()
            
            if not positions:
                logger.info("📝 No previous positions found in database")
                return {}
            
            # Batch load DCA metadata for all positions
            position_states = await self._batch_restore_positions(positions)
            
            if position_states:
                logger.info(f"✅ Restored {len(position_states)} positions from database")
                self._log_restoration_summary(position_states)
            
            return position_states
            
        except Exception as e:
            logger.error(f"❌ Failed to restore positions from database: {e}")
            return {}
    
    async def _batch_restore_positions(self, positions: List) -> Dict[str, PositionState]:
        """
        Batch restore positions with parallel DCA metadata loading.
        
        Args:
            positions: List of database position objects
            
        Returns:
            Dictionary mapping symbol to PositionState
        """
        # Create tasks for parallel loading
        restore_tasks = [
            self._restore_single_position(pos)
            for pos in positions
            if pos.quantity != 0
        ]
        
        # Execute in parallel
        restored = await asyncio.gather(*restore_tasks, return_exceptions=True)
        
        # Filter out errors and build result dict
        position_states = {}
        for result in restored:
            if isinstance(result, Exception):
                logger.error(f"Error restoring position: {result}")
                continue
            if result:
                symbol, state = result
                position_states[symbol] = state
        
        return position_states
    
    async def _restore_single_position(self, pos) -> Optional[tuple[str, PositionState]]:
        """
        Restore a single position with DCA metadata.
        
        Args:
            pos: Database position object
            
        Returns:
            Tuple of (symbol, PositionState) or None if restoration fails
        """
        try:
            direction = PositionDirection.LONG if pos.quantity > 0 else PositionDirection.SHORT
            
            # Load DCA metadata
            dca_history = await self._load_position_dca_metadata(pos.symbol, direction)
            
            # Log restoration details
            self._log_position_restoration(pos, direction, dca_history)
            
            # Create position state
            position_state = PositionState(
                symbol=pos.symbol,
                direction=direction,
                phase=TradePhase.ENTRY,  # Start in entry phase, will be updated by monitoring
                quantity=abs(pos.quantity),
                average_price=pos.avg_price,
                current_price=pos.avg_price,  # Will be updated with real market price
                entry_time=pos.entry_time or datetime.now(),
                averaging_attempts=dca_history['attempts'],
                last_dca_price=dca_history['last_price'],
                dca_order_prices=dca_history['prices'].copy(),
                position_lifecycle_id=dca_history['lifecycle_id']
            )
            
            return (pos.symbol, position_state)
            
        except Exception as e:
            logger.error(f"Failed to restore position {pos.symbol}: {e}")
            return None
    
    async def _load_position_dca_metadata(
        self, 
        symbol: str, 
        direction: PositionDirection
    ) -> dict:
        """
        Load DCA metadata from database using position lifecycle approach.
        
        Args:
            symbol: Symbol to load metadata for
            direction: Position direction
            
        Returns:
            Dict with 'attempts', 'prices', 'last_price', and 'lifecycle_id' keys
        """
        try:
            logger.info(f"🔍 LOADING DCA METADATA: {symbol} ({direction.value})")
            
            # Try to load from DCA metadata manager first
            if self.dca_metadata_manager:
                try:
                    metadata = await self.dca_metadata_manager.get_active_metadata(
                        symbol=symbol,
                        direction=direction.value.lower()
                    )
                    
                    if metadata:
                        logger.info(
                            f"✅ LOADED DCA METADATA: {symbol}\n"
                            f"   Lifecycle ID: {metadata['position_lifecycle_id'][:8]}...\n"
                            f"   DCA Attempts: {metadata['dca_attempts']}\n"
                            f"   DCA Prices: {[f'${p:.2f}' for p in metadata['dca_prices']]}\n"
                            f"   Last DCA Price: ${metadata['last_dca_price']:.2f}" 
                            if metadata['last_dca_price'] else "None"
                        )
                        
                        return {
                            'attempts': metadata['dca_attempts'],
                            'prices': metadata['dca_prices'],
                            'last_price': metadata['last_dca_price'],
                            'lifecycle_id': metadata['position_lifecycle_id']
                        }
                except Exception as e:
                    logger.warning(
                        f"⚠️ Failed to load DCA metadata from database for {symbol}: {e}"
                    )
            
            # No existing metadata found - start fresh with new lifecycle ID
            new_lifecycle_id = str(uuid.uuid4())
            
            logger.info(
                f"📝 FRESH DCA TRACKING: {symbol} - starting new lifecycle\n"
                f"   New Lifecycle ID: {new_lifecycle_id[:8]}..."
            )
            
            return {
                'attempts': 0,
                'prices': [],
                'last_price': None,
                'lifecycle_id': new_lifecycle_id
            }
            
        except Exception as e:
            logger.warning(f"Could not load DCA metadata for {symbol}: {e}")
            fallback_lifecycle_id = str(uuid.uuid4())
            return {
                'attempts': 0,
                'prices': [],
                'last_price': None,
                'lifecycle_id': fallback_lifecycle_id
            }
    
    def _log_position_restoration(
        self, 
        pos, 
        direction: PositionDirection, 
        dca_history: dict
    ) -> None:
        """Log detailed position restoration information."""
        logger.info(
            f"🔄 RESTORING POSITION: {pos.symbol}\n"
            f"   Direction: {direction.value}\n"
            f"   Quantity: {pos.quantity}\n"
            f"   Average Price: ${pos.avg_price:.2f}\n"
            f"   Lifecycle ID: {dca_history['lifecycle_id'][:8]}...\n"
            f"   Calculated DCA Attempts: {dca_history['attempts']}\n"
            f"   DCA Price History: {[f'${p:.2f}' for p in dca_history['prices']]}\n"
            f"   Last DCA Price: ${dca_history['last_price']:.2f}" 
            if dca_history['last_price'] else "   Last DCA Price: None"
        )
    
    def _log_restoration_summary(self, position_states: Dict[str, PositionState]) -> None:
        """Log summary of all restored positions."""
        print(f"\n🔄 RESTORED {len(position_states)} POSITIONS FROM DATABASE:")
        for symbol, pos in position_states.items():
            print(
                f"   {symbol}: {pos.direction.value} {pos.quantity} "
                f"@ {pos.average_price:.2f} (DCA: {pos.averaging_attempts}/3)"
            )
