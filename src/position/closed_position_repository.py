"""
Closed Position Repository

Fetches historical closed positions for confidence drift analysis.
Queries the last N closed positions to establish baseline for factor performance.

Usage:
    repo = ClosedPositionRepository(db_manager)
    snapshots = await repo.fetch_last_n(n=50)
    
    for snapshot in snapshots:
        logger.info(f"{snapshot.symbol}: {snapshot.realized_pnl_percent:.2f}%")
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging_config import get_logger
from src.database.enhanced_schema import EnhancedPositionRecord


logger = get_logger(__name__)


@dataclass(frozen=True)
class ClosedPositionSnapshot:
    """Snapshot of a closed position for historical analysis.
    
    Attributes:
        symbol: Trading symbol (e.g., 'AAPL')
        direction: Position direction ('long' or 'short')
        realized_pnl_percent: Realized P&L as percentage
        confidence_score: Entry confidence score (if available)
        closed_at: Timestamp when position was closed
    """
    symbol: str
    direction: str
    realized_pnl_percent: float
    confidence_score: Optional[float]
    closed_at: datetime


class ClosedPositionRepository:
    """Repository for querying historical closed positions.
    
    Provides access to closed position data for drift analysis and
    confidence calibration based on realized outcomes.
    
    Attributes:
        db_manager: Database manager instance
    """
    
    def __init__(self, db_manager):
        """Initialize closed position repository.
        
        Args:
            db_manager: DatabaseManager instance for database access
        """
        self.db_manager = db_manager
        logger.info("ClosedPositionRepository initialized")
    
    async def fetch_last_n(self, n: int = 50) -> List[ClosedPositionSnapshot]:
        """Fetch the last N closed positions ordered by close time.
        
        Args:
            n: Number of closed positions to fetch (default: 50)
        
        Returns:
            List of ClosedPositionSnapshot ordered by closed_at descending
        """
        try:
            async with self.db_manager.get_session() as session:
                # Query closed positions
                stmt = (
                    select(EnhancedPositionRecord)
                    .where(EnhancedPositionRecord.status == 'closed')
                    .where(EnhancedPositionRecord.closed_at.isnot(None))
                    .order_by(EnhancedPositionRecord.closed_at.desc())
                    .limit(n)
                )
                
                result = await session.execute(stmt)
                positions = result.scalars().all()
                
                # Convert to snapshots
                snapshots = []
                for pos in positions:
                    # Try to get confidence score from metadata if available
                    confidence_score = None
                    # TODO: Extract from position metadata once confidence tracking is implemented
                    
                    snapshot = ClosedPositionSnapshot(
                        symbol=pos.symbol,
                        direction=pos.direction,
                        realized_pnl_percent=pos.realized_pnl_percent,
                        confidence_score=confidence_score,
                        closed_at=pos.closed_at
                    )
                    snapshots.append(snapshot)
                
                logger.info(
                    f"Fetched {len(snapshots)} closed positions",
                    extra={
                        "component": "ClosedPositionRepository",
                        "requested": n,
                        "retrieved": len(snapshots)
                    }
                )
                
                return snapshots
                
        except Exception as e:
            logger.error(
                f"Failed to fetch closed positions: {e}",
                extra={
                    "component": "ClosedPositionRepository",
                    "requested_count": n,
                    "error": str(e)
                },
                exc_info=True
            )
            return []
    
    async def fetch_last_n_with_confidence(
        self,
        n: int = 50,
        min_confidence: Optional[float] = None
    ) -> List[ClosedPositionSnapshot]:
        """Fetch closed positions that have confidence scores.
        
        Args:
            n: Number of positions to fetch
            min_confidence: Minimum confidence score filter (optional)
        
        Returns:
            List of ClosedPositionSnapshot with confidence scores
        """
        all_snapshots = await self.fetch_last_n(n=n * 2)  # Fetch more since filtering
        
        # Filter for positions with confidence scores
        with_confidence = [
            s for s in all_snapshots
            if s.confidence_score is not None
        ]
        
        # Apply minimum confidence filter if specified
        if min_confidence is not None:
            with_confidence = [
                s for s in with_confidence
                if s.confidence_score >= min_confidence
            ]
        
        # Return up to n results
        result = with_confidence[:n]
        
        logger.info(
            f"Fetched {len(result)} closed positions with confidence scores",
            extra={
                "component": "ClosedPositionRepository",
                "requested": n,
                "retrieved": len(result),
                "min_confidence": min_confidence
            }
        )
        
        return result
    
    async def get_average_pnl(self, n: int = 50) -> Optional[float]:
        """Calculate average realized P&L % from last N closed positions.
        
        Args:
            n: Number of positions to include in average
        
        Returns:
            Average realized P&L percentage or None if no positions
        """
        snapshots = await self.fetch_last_n(n=n)
        
        if not snapshots:
            return None
        
        avg_pnl = sum(s.realized_pnl_percent for s in snapshots) / len(snapshots)
        
        logger.debug(
            f"Average P&L: {avg_pnl:.2f}% from {len(snapshots)} positions",
            extra={
                "component": "ClosedPositionRepository",
                "count": len(snapshots),
                "avg_pnl": avg_pnl
            }
        )
        
        return avg_pnl
