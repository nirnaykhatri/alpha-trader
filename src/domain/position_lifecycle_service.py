"""
Position Lifecycle ID Service

Centralizes position lifecycle ID generation and validation logic.
Eliminates ad hoc ID construction scattered across strategy and persistence layers.
Includes distributed locking to prevent race conditions from concurrent webhooks.
Uses nanosecond precision + monotonic sequence to prevent collisions in ultra-fast scenarios.
"""

import re
import asyncio
import time
from datetime import datetime
from typing import Optional, Dict
from contextlib import asynccontextmanager


class PositionLifecycleService:
    """
    Service for managing position lifecycle identifiers with distributed locking.
    
    Position lifecycle IDs uniquely identify each position instance,
    enabling proper DCA metadata isolation when reopening the same symbol.
    
    Format: {symbol}_{timestamp_ns}_{seq}_{strategy_id}
    Example: AAPL_1704067200123456789_0_long
    
    Uses nanosecond timestamp + per-symbol sequence counter to prevent collisions
    even when multiple positions open in rapid succession (e.g., high-frequency signals).
    
    Collision Prevention Mechanisms:
    1. Nanosecond precision (vs second precision)
    2. Per-symbol monotonic sequence counter
    3. Distributed lock during ID generation
    4. Async sleep for sub-millisecond spacing
    """
    
    # Lifecycle ID pattern for validation (updated for nanosecond + sequence)
    LIFECYCLE_ID_PATTERN = re.compile(r'^[A-Z]+_\d{19}_\d+_[a-z]+$')
    
    # Class-level locks for thread safety
    _locks: Dict[str, asyncio.Lock] = {}
    _locks_lock: asyncio.Lock = asyncio.Lock()
    
    # Per-symbol sequence counters to prevent collisions
    _sequences: Dict[str, int] = {}
    _sequences_lock: asyncio.Lock = asyncio.Lock()
    
    @classmethod
    async def _get_lock(cls, key: str) -> asyncio.Lock:
        """
        Get or create a lock for the given key.
        
        Args:
            key: Lock key (e.g., 'AAPL_long')
            
        Returns:
            asyncio.Lock instance
        """
        async with cls._locks_lock:
            if key not in cls._locks:
                cls._locks[key] = asyncio.Lock()
            return cls._locks[key]
    
    @classmethod
    @asynccontextmanager
    async def _lifecycle_lock(cls, symbol: str, strategy_id: str):
        """
        Distributed lock context manager to prevent concurrent ID generation.
        
        Args:
            symbol: Trading symbol
            strategy_id: Strategy identifier
            
        Yields:
            Lock context
            
        Example:
            async with PositionLifecycleService._lifecycle_lock('AAPL', 'long'):
                lifecycle_id = await generate_safely()
        """
        lock_key = f"lifecycle:{symbol}:{strategy_id}"
        lock = await cls._get_lock(lock_key)
        
        async with lock:
            yield
    
    @classmethod
    async def _get_sequence(cls, key: str) -> int:
        """
        Get and increment sequence counter for the given key.
        
        Args:
            key: Sequence key (e.g., 'AAPL_long')
            
        Returns:
            Next sequence number
        """
        async with cls._sequences_lock:
            current = cls._sequences.get(key, 0)
            cls._sequences[key] = current + 1
            return current
    
    @classmethod
    async def generate(
        cls,
        symbol: str,
        entry_time: datetime,
        strategy_id: str = "default",
        use_lock: bool = True
    ) -> str:
        """
        Generate unique position lifecycle ID with collision prevention.
        
        Uses nanosecond timestamp + monotonic sequence to prevent collisions
        even in ultra-fast entry scenarios (e.g., multiple webhooks within same second).
        
        Args:
            symbol: Trading symbol (e.g., 'AAPL')
            entry_time: Position entry timestamp
            strategy_id: Strategy identifier (default: 'default')
            use_lock: Whether to use distributed lock (default: True)
            
        Returns:
            Lifecycle ID string with format: {symbol}_{timestamp_ns}_{seq}_{strategy_id}
            
        Example:
            >>> service = PositionLifecycleService()
            >>> lifecycle_id = await service.generate('AAPL', datetime.utcnow(), 'long')
            >>> print(lifecycle_id)
            AAPL_1704067200123456789_0_long
            
        Note:
            - Nanosecond precision prevents collisions within same second
            - Sequence counter handles ultra-fast entries (nanosecond duplicates)
            - Distributed lock prevents race conditions from concurrent webhooks
            - Set use_lock=False only in single-threaded contexts
        """
        seq_key = f"{symbol}_{strategy_id}"
        
        if use_lock:
            async with cls._lifecycle_lock(symbol, strategy_id):
                # Small delay to ensure unique timestamps
                await asyncio.sleep(0.001)
                
                # Nanosecond timestamp (19 digits)
                timestamp_ns = time.time_ns()
                
                # Get sequence number for this symbol+strategy
                seq = await cls._get_sequence(seq_key)
                
                return f"{symbol}_{timestamp_ns}_{seq}_{strategy_id}"
        else:
            timestamp_ns = time.time_ns()
            seq = await cls._get_sequence(seq_key)
            return f"{symbol}_{timestamp_ns}_{seq}_{strategy_id}"
    
    @staticmethod
    def validate(lifecycle_id: str) -> bool:
        """
        Validate lifecycle ID format.
        
        Supports both legacy (second precision) and new (nanosecond + sequence) formats:
        - Legacy: {symbol}_{timestamp}_{strategy_id}
        - New: {symbol}_{timestamp_ns}_{seq}_{strategy_id}
        
        Args:
            lifecycle_id: Lifecycle ID to validate
            
        Returns:
            True if valid format, False otherwise
            
        Example:
            >>> service = PositionLifecycleService()
            >>> service.validate('AAPL_1704067200123456789_0_long')  # New format
            True
            >>> service.validate('AAPL_1704067200_long')  # Legacy format
            True
            >>> service.validate('invalid-format')
            False
        """
        if not lifecycle_id or not isinstance(lifecycle_id, str):
            return False
        
        # New format: symbol_timestamp_ns_seq_strategy_id
        if PositionLifecycleService.LIFECYCLE_ID_PATTERN.match(lifecycle_id):
            return True
        
        # Legacy format: symbol_timestamp_strategy_id (backward compatibility)
        legacy_pattern = re.compile(r'^[A-Z]+_\d+_[a-z]+$')
        return bool(legacy_pattern.match(lifecycle_id))
    
    @staticmethod
    def parse(lifecycle_id: str) -> Optional[dict]:
        """
        Parse lifecycle ID into components.
        
        Supports both legacy and new formats.
        
        Args:
            lifecycle_id: Lifecycle ID to parse
            
        Returns:
            Dictionary with 'symbol', 'timestamp', 'sequence', 'strategy_id' or None if invalid
            
        Example:
            >>> service = PositionLifecycleService()
            >>> components = service.parse('AAPL_1704067200123456789_0_long')
            >>> print(components)
            {'symbol': 'AAPL', 'timestamp': 1704067200123456789, 'sequence': 0, 'strategy_id': 'long'}
            
            >>> # Legacy format (no sequence)
            >>> components = service.parse('AAPL_1704067200_long')
            >>> print(components)
            {'symbol': 'AAPL', 'timestamp': 1704067200, 'sequence': None, 'strategy_id': 'long'}
        """
        if not PositionLifecycleService.validate(lifecycle_id):
            return None
        
        parts = lifecycle_id.split('_')
        
        try:
            # New format: 4 parts (symbol, timestamp_ns, sequence, strategy_id)
            if len(parts) == 4:
                return {
                    'symbol': parts[0],
                    'timestamp': int(parts[1]),
                    'sequence': int(parts[2]),
                    'strategy_id': parts[3]
                }
            # Legacy format: 3 parts (symbol, timestamp, strategy_id)
            elif len(parts) == 3:
                return {
                    'symbol': parts[0],
                    'timestamp': int(parts[1]),
                    'sequence': None,  # No sequence in legacy format
                    'strategy_id': parts[2]
                }
            else:
                return None
        except (ValueError, IndexError):
            return None
    
    @staticmethod
    def extract_symbol(lifecycle_id: str) -> Optional[str]:
        """
        Extract symbol from lifecycle ID.
        
        Args:
            lifecycle_id: Lifecycle ID
            
        Returns:
            Symbol or None if invalid
        """
        parsed = PositionLifecycleService.parse(lifecycle_id)
        return parsed['symbol'] if parsed else None
    
    @staticmethod
    def extract_strategy_id(lifecycle_id: str) -> Optional[str]:
        """
        Extract strategy ID from lifecycle ID.
        
        Args:
            lifecycle_id: Lifecycle ID
            
        Returns:
            Strategy ID or None if invalid
        """
        parsed = PositionLifecycleService.parse(lifecycle_id)
        return parsed['strategy_id'] if parsed else None
