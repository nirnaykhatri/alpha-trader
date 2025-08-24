"""
Database Schema Extension for DCA Metadata Persistence
This extends the existing database to store DCA tracking information per position lifecycle.
"""

from sqlalchemy import Column, String, Float, Integer, DateTime, Text, JSON
from sqlalchemy.orm import declarative_base
from datetime import datetime
import json
import uuid
from typing import List, Optional, Dict, Any

# Extend the existing database schema
Base = declarative_base()

class DCAMetadataRecord(Base):
    """
    Database model for DCA metadata per position lifecycle.
    This solves the order history pollution problem by tracking DCA info per position.
    """
    __tablename__ = 'dca_metadata'
    
    # Primary key combining symbol and position lifecycle ID
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False, index=True)
    position_lifecycle_id = Column(String(50), nullable=False, index=True)  # UUID for each position cycle
    
    # Position direction and basic info
    direction = Column(String(10), nullable=False)  # 'long' or 'short'
    entry_price = Column(Float, nullable=False)
    entry_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # DCA tracking information
    dca_attempts = Column(Integer, nullable=False, default=0)
    last_dca_price = Column(Float, nullable=True)
    dca_order_prices_json = Column(Text, nullable=True)  # JSON array of DCA prices
    
    # Position status
    is_active = Column(String(10), nullable=False, default='true')  # 'true'/'false'
    closed_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    def get_dca_order_prices(self) -> List[float]:
        """Get DCA order prices as a list."""
        if not self.dca_order_prices_json:
            return []
        try:
            return json.loads(self.dca_order_prices_json)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_dca_order_prices(self, prices: List[float]) -> None:
        """Set DCA order prices from a list."""
        self.dca_order_prices_json = json.dumps(prices)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'symbol': self.symbol,
            'position_lifecycle_id': self.position_lifecycle_id,
            'direction': self.direction,
            'entry_price': self.entry_price,
            'entry_time': self.entry_time.isoformat() if self.entry_time else None,
            'dca_attempts': self.dca_attempts,
            'last_dca_price': self.last_dca_price,
            'dca_order_prices': self.get_dca_order_prices(),
            'is_active': self.is_active == 'true',
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class DCAMetadataManager:
    """
    Manager class for DCA metadata operations.
    Provides clean API for storing and retrieving DCA tracking information.
    """
    
    def __init__(self, database_manager):
        """Initialize with existing database manager."""
        self.db = database_manager
        self._ensure_table_exists()
    
    def _ensure_table_exists(self):
        """Ensure DCA metadata table exists in the database."""
        try:
            # This would be called during database initialization
            # The actual table creation would be handled by the main database manager
            pass
        except Exception as e:
            print(f"Warning: Could not ensure DCA metadata table exists: {e}")
    
    async def create_position_lifecycle(self, symbol: str, direction: str, 
                                      entry_price: float) -> str:
        """
        Create a new position lifecycle for DCA tracking.
        
        Args:
            symbol: Trading symbol
            direction: 'long' or 'short'
            entry_price: Entry price for the position
            
        Returns:
            position_lifecycle_id: Unique ID for this position cycle
        """
        import uuid
        position_lifecycle_id = str(uuid.uuid4())
        
        try:
            session = self.db._session_factory()
            try:
                metadata_record = DCAMetadataRecord(
                    symbol=symbol,
                    position_lifecycle_id=position_lifecycle_id,
                    direction=direction,
                    entry_price=entry_price,
                    dca_attempts=0,
                    last_dca_price=None,
                    dca_order_prices_json='[]',
                    is_active='true'
                )
                
                session.add(metadata_record)
                session.commit()
                
                print(f"✅ Created DCA lifecycle: {symbol} {direction} @ ${entry_price:.2f} (ID: {position_lifecycle_id[:8]}...)")
                return position_lifecycle_id
                
            finally:
                session.close()
                
        except Exception as e:
            print(f"❌ Failed to create DCA lifecycle for {symbol}: {e}")
            # Return a temporary ID for fallback
            return position_lifecycle_id
    
    async def update_dca_metadata(self, position_lifecycle_id: str, 
                                dca_attempts: int, dca_order_prices: List[float], 
                                last_dca_price: Optional[float]) -> bool:
        """
        Update DCA metadata for a position lifecycle.
        
        Args:
            position_lifecycle_id: Position lifecycle ID
            dca_attempts: Number of DCA attempts
            dca_order_prices: List of DCA order prices
            last_dca_price: Last DCA price
            
        Returns:
            True if successful, False otherwise
        """
        try:
            session = self.db._session_factory()
            try:
                # Import the record class (would be properly imported in real implementation)
                from src.database.database_manager import DCAMetadataRecord
                
                metadata_record = session.query(DCAMetadataRecord).filter_by(
                    position_lifecycle_id=position_lifecycle_id,
                    is_active='true'
                ).first()
                
                if metadata_record:
                    metadata_record.dca_attempts = dca_attempts
                    metadata_record.last_dca_price = last_dca_price
                    metadata_record.set_dca_order_prices(dca_order_prices)
                    metadata_record.updated_at = datetime.utcnow()
                    
                    session.commit()
                    
                    print(f"💾 Updated DCA metadata: {metadata_record.symbol} "
                          f"attempts={dca_attempts}, last_price=${last_dca_price:.2f if last_dca_price else 0:.2f}")
                    return True
                else:
                    print(f"⚠️ DCA metadata record not found: {position_lifecycle_id}")
                    return False
                    
            finally:
                session.close()
                
        except Exception as e:
            print(f"❌ Failed to update DCA metadata: {e}")
            return False
    
    async def get_dca_metadata(self, position_lifecycle_id: str) -> Optional[Dict[str, Any]]:
        """
        Get DCA metadata for a position lifecycle.
        
        Args:
            position_lifecycle_id: Position lifecycle ID
            
        Returns:
            DCA metadata dictionary or None
        """
        try:
            session = self.db._session_factory()
            try:
                # Import the record class (would be properly imported in real implementation)
                from src.database.database_manager import DCAMetadataRecord
                
                metadata_record = session.query(DCAMetadataRecord).filter_by(
                    position_lifecycle_id=position_lifecycle_id,
                    is_active='true'
                ).first()
                
                if metadata_record:
                    return {
                        'attempts': metadata_record.dca_attempts,
                        'prices': metadata_record.get_dca_order_prices(),
                        'last_price': metadata_record.last_dca_price
                    }
                else:
                    return None
                    
            finally:
                session.close()
                
        except Exception as e:
            print(f"❌ Failed to get DCA metadata: {e}")
            return None
    
    async def close_position_lifecycle(self, position_lifecycle_id: str) -> bool:
        """
        Mark a position lifecycle as closed.
        
        Args:
            position_lifecycle_id: Position lifecycle ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            session = self.db._session_factory()
            try:
                # Import the record class (would be properly imported in real implementation)
                from src.database.database_manager import DCAMetadataRecord
                
                metadata_record = session.query(DCAMetadataRecord).filter_by(
                    position_lifecycle_id=position_lifecycle_id,
                    is_active='true'
                ).first()
                
                if metadata_record:
                    metadata_record.is_active = 'false'
                    metadata_record.closed_at = datetime.utcnow()
                    metadata_record.updated_at = datetime.utcnow()
                    
                    session.commit()
                    
                    print(f"🔐 Closed DCA lifecycle: {metadata_record.symbol} (ID: {position_lifecycle_id[:8]}...)")
                    return True
                else:
                    print(f"⚠️ DCA metadata record not found for closure: {position_lifecycle_id}")
                    return False
                    
            finally:
                session.close()
                
        except Exception as e:
            print(f"❌ Failed to close DCA lifecycle: {e}")
            return False
    
    async def get_active_dca_metadata_for_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get active DCA metadata for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            DCA metadata dictionary or None
        """
        try:
            session = self.db._session_factory()
            try:
                # Import the record class (would be properly imported in real implementation)
                from src.database.database_manager import DCAMetadataRecord
                
                metadata_record = session.query(DCAMetadataRecord).filter_by(
                    symbol=symbol,
                    is_active='true'
                ).order_by(DCAMetadataRecord.created_at.desc()).first()
                
                if metadata_record:
                    return {
                        'position_lifecycle_id': metadata_record.position_lifecycle_id,
                        'attempts': metadata_record.dca_attempts,
                        'prices': metadata_record.get_dca_order_prices(),
                        'last_price': metadata_record.last_dca_price,
                        'direction': metadata_record.direction,
                        'entry_price': metadata_record.entry_price
                    }
                else:
                    return None
                    
            finally:
                session.close()
                
        except Exception as e:
            print(f"❌ Failed to get active DCA metadata for {symbol}: {e}")
            return None

    async def get_active_metadata(self, symbol: str, direction: str) -> Optional[Dict[str, Any]]:
        """
        Get active DCA metadata for a symbol and direction (for compatibility with tests).
        
        Args:
            symbol: Trading symbol
            direction: Position direction ('long' or 'short')
            
        Returns:
            DCA metadata dictionary with position_lifecycle_id or None
        """
        try:
            session = self.db._session_factory()
            try:
                # Query for active metadata with matching symbol and direction
                metadata_record = session.query(DCAMetadataRecord).filter(
                    DCAMetadataRecord.symbol == symbol,
                    DCAMetadataRecord.direction == direction.lower(),
                    DCAMetadataRecord.is_active == True
                ).first()
                
                if metadata_record:
                    return {
                        'position_lifecycle_id': metadata_record.position_lifecycle_id,
                        'dca_attempts': metadata_record.dca_attempts,
                        'dca_prices': metadata_record.get_dca_order_prices(),
                        'last_dca_price': metadata_record.last_dca_price,
                        'direction': metadata_record.direction,
                        'entry_price': metadata_record.entry_price
                    }
                else:
                    return None
                    
            finally:
                session.close()
                
        except Exception as e:
            print(f"❌ Failed to get active metadata for {symbol} {direction}: {e}")
            return None
