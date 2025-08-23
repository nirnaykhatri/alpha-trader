"""
Enhanced Database Schema for Transparent Position and DCA Tracking
This provides comprehensive tracking for localhost endpoints with complete visibility.
"""

from sqlalchemy import Column, String, Float, Integer, DateTime, Text, JSON, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import json
import uuid
from typing import List, Optional, Dict, Any

Base = declarative_base()

class EnhancedPositionRecord(Base):
    """
    Enhanced position record with comprehensive tracking for localhost endpoints.
    """
    __tablename__ = 'enhanced_positions'
    
    # Primary identification
    position_id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol = Column(String(10), nullable=False, index=True)
    position_lifecycle_id = Column(String(50), nullable=False, index=True)
    
    # Position basics
    direction = Column(String(10), nullable=False)  # 'long' or 'short'
    status = Column(String(20), nullable=False, default='active')  # 'active', 'closed'
    
    # Entry information
    entry_price = Column(Float, nullable=False)
    entry_quantity = Column(Float, nullable=False)
    entry_time = Column(DateTime, nullable=False)
    entry_order_id = Column(String(50), nullable=False)
    
    # Current position state
    current_quantity = Column(Float, nullable=False)
    current_avg_price = Column(Float, nullable=False)
    current_market_price = Column(Float, nullable=False)
    
    # P&L calculations
    unrealized_pnl = Column(Float, nullable=False, default=0.0)
    unrealized_pnl_percent = Column(Float, nullable=False, default=0.0)
    realized_pnl = Column(Float, nullable=False, default=0.0)
    
    # DCA summary (for quick access)
    total_dca_attempts = Column(Integer, nullable=False, default=0)
    total_invested = Column(Float, nullable=False)
    
    # Risk management
    max_loss_threshold = Column(Float, nullable=True)
    profit_target = Column(Float, nullable=True)
    trailing_stop_active = Column(Boolean, nullable=False, default=False)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    
    # Relationships
    dca_orders = relationship("DCAOrderRecord", back_populates="position", cascade="all, delete-orphan")
    
    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses with complete transparency."""
        return {
            'position_id': self.position_id,
            'symbol': self.symbol,
            'position_lifecycle_id': self.position_lifecycle_id,
            'direction': self.direction,
            'status': self.status,
            
            # Entry details
            'entry': {
                'price': self.entry_price,
                'quantity': self.entry_quantity,
                'time': self.entry_time.isoformat() if self.entry_time else None,
                'order_id': self.entry_order_id
            },
            
            # Current state
            'current': {
                'quantity': self.current_quantity,
                'avg_price': self.current_avg_price,
                'market_price': self.current_market_price,
                'total_invested': self.total_invested
            },
            
            # P&L
            'pnl': {
                'unrealized': self.unrealized_pnl,
                'unrealized_percent': self.unrealized_pnl_percent,
                'realized': self.realized_pnl
            },
            
            # DCA summary
            'dca_summary': {
                'total_attempts': self.total_dca_attempts,
                'has_dca_orders': len(self.dca_orders) > 0 if self.dca_orders else False
            },
            
            # Risk management
            'risk_management': {
                'max_loss_threshold': self.max_loss_threshold,
                'profit_target': self.profit_target,
                'trailing_stop_active': self.trailing_stop_active
            },
            
            # Timestamps
            'timestamps': {
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None,
                'closed_at': self.closed_at.isoformat() if self.closed_at else None
            }
        }

class DCAOrderRecord(Base):
    """
    Individual DCA order tracking with complete transparency.
    Each DCA attempt gets its own record for detailed analysis.
    """
    __tablename__ = 'dca_orders'
    
    # Primary identification
    dca_order_id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    position_id = Column(String(50), ForeignKey('enhanced_positions.position_id'), nullable=False)
    order_id = Column(String(50), nullable=False, index=True)  # Broker order ID
    
    # DCA sequence
    dca_attempt_number = Column(Integer, nullable=False)  # 1, 2, 3, etc.
    
    # Order details
    side = Column(String(10), nullable=False)  # 'buy' or 'sell'
    quantity_requested = Column(Float, nullable=False)
    price_requested = Column(Float, nullable=True)  # None for market orders
    order_type = Column(String(20), nullable=False)  # 'market', 'limit'
    
    # Technical analysis context
    technical_reason = Column(String(50), nullable=True)  # 'support_breach', 'resistance_breach'
    technical_level = Column(Float, nullable=True)  # The support/resistance level
    technical_confidence = Column(Float, nullable=True)  # Confidence in the technical level
    timeframe_used = Column(String(10), nullable=True)  # '15m', '1h', etc.
    
    # Execution details
    status = Column(String(20), nullable=False, default='pending')  # 'pending', 'filled', 'partially_filled', 'canceled'
    quantity_filled = Column(Float, nullable=False, default=0.0)
    average_fill_price = Column(Float, nullable=True)
    
    # Position impact
    position_avg_before = Column(Float, nullable=False)  # Position average before this DCA
    position_avg_after = Column(Float, nullable=True)   # Position average after this DCA
    quantity_before = Column(Float, nullable=False)      # Position quantity before this DCA
    quantity_after = Column(Float, nullable=True)       # Position quantity after this DCA
    
    # Progressive validation
    last_dca_price = Column(Float, nullable=True)      # Previous DCA price for validation
    is_progressive = Column(Boolean, nullable=False)    # Whether this DCA was progressive
    progression_improvement_pct = Column(Float, nullable=True)  # How much better than last DCA
    
    # Timestamps
    placed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    filled_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationship
    position = relationship("EnhancedPositionRecord", back_populates="dca_orders")
    
    def to_api_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            'dca_order_id': self.dca_order_id,
            'order_id': self.order_id,
            'attempt_number': self.dca_attempt_number,
            
            # Order details
            'order': {
                'side': self.side,
                'quantity_requested': self.quantity_requested,
                'price_requested': self.price_requested,
                'order_type': self.order_type,
                'status': self.status
            },
            
            # Technical context
            'technical_analysis': {
                'reason': self.technical_reason,
                'level': self.technical_level,
                'confidence': self.technical_confidence,
                'timeframe': self.timeframe_used
            },
            
            # Execution
            'execution': {
                'quantity_filled': self.quantity_filled,
                'average_fill_price': self.average_fill_price,
                'fill_percentage': (self.quantity_filled / self.quantity_requested * 100) if self.quantity_requested > 0 else 0
            },
            
            # Position impact
            'position_impact': {
                'avg_price_before': self.position_avg_before,
                'avg_price_after': self.position_avg_after,
                'quantity_before': self.quantity_before,
                'quantity_after': self.quantity_after
            },
            
            # Progressive validation
            'progressive_validation': {
                'last_dca_price': self.last_dca_price,
                'is_progressive': self.is_progressive,
                'improvement_percent': self.progression_improvement_pct
            },
            
            # Timestamps
            'timestamps': {
                'placed_at': self.placed_at.isoformat() if self.placed_at else None,
                'filled_at': self.filled_at.isoformat() if self.filled_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None
            }
        }

class PositionSummaryView:
    """
    Virtual view for comprehensive position summary for localhost endpoints.
    This aggregates data from multiple tables for transparency.
    """
    
    @staticmethod
    def get_position_summary(session, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get comprehensive position summary with all DCA details.
        Perfect for localhost /positions endpoint.
        """
        try:
            query = session.query(EnhancedPositionRecord)
            
            if symbol:
                query = query.filter(EnhancedPositionRecord.symbol == symbol)
            
            positions = query.filter(EnhancedPositionRecord.status == 'active').all()
            
            summaries = []
            for position in positions:
                # Get DCA order details
                dca_orders = sorted(position.dca_orders, key=lambda x: x.dca_attempt_number)
                
                # Calculate DCA statistics
                filled_dcas = [dca for dca in dca_orders if dca.status == 'filled']
                pending_dcas = [dca for dca in dca_orders if dca.status == 'pending']
                
                summary = {
                    **position.to_api_dict(),
                    
                    # Enhanced DCA details
                    'dca_details': {
                        'total_attempts': len(dca_orders),
                        'filled_attempts': len(filled_dcas),
                        'pending_attempts': len(pending_dcas),
                        'dca_orders': [dca.to_api_dict() for dca in dca_orders],
                        
                        # DCA price progression
                        'price_progression': [
                            {
                                'attempt': dca.dca_attempt_number,
                                'price': dca.average_fill_price or dca.price_requested,
                                'filled': dca.status == 'filled'
                            }
                            for dca in dca_orders
                        ],
                        
                        # Progressive validation summary
                        'progressive_summary': {
                            'all_progressive': all(dca.is_progressive for dca in filled_dcas),
                            'average_improvement': sum(dca.progression_improvement_pct or 0 for dca in filled_dcas) / len(filled_dcas) if filled_dcas else 0
                        }
                    },
                    
                    # Real-time calculations
                    'real_time': {
                        'market_value': position.current_quantity * position.current_market_price,
                        'cost_basis': position.current_quantity * position.current_avg_price,
                        'position_age_hours': (datetime.utcnow() - position.created_at).total_seconds() / 3600 if position.created_at else 0
                    }
                }
                
                summaries.append(summary)
            
            return summaries
            
        except Exception as e:
            print(f"Error getting position summary: {e}")
            return []

# Database manager extension
class EnhancedDatabaseManager:
    """
    Enhanced database manager with comprehensive position and DCA tracking.
    """
    
    def __init__(self, database_manager):
        self.db = database_manager
        self._ensure_enhanced_tables()
    
    def _ensure_enhanced_tables(self):
        """Ensure enhanced tables exist."""
        try:
            # This would create the enhanced tables
            Base.metadata.create_all(self.db.engine)
        except Exception as e:
            print(f"Warning: Could not create enhanced tables: {e}")
    
    async def create_enhanced_position(self, symbol: str, direction: str, entry_price: float, 
                                     entry_quantity: float, entry_order_id: str, 
                                     position_lifecycle_id: str) -> str:
        """Create a new enhanced position record."""
        session = self.db._session_factory()
        try:
            position = EnhancedPositionRecord(
                symbol=symbol,
                position_lifecycle_id=position_lifecycle_id,
                direction=direction,
                entry_price=entry_price,
                entry_quantity=entry_quantity,
                current_quantity=entry_quantity,
                current_avg_price=entry_price,
                current_market_price=entry_price,
                total_invested=entry_quantity * entry_price,
                entry_time=datetime.utcnow(),
                entry_order_id=entry_order_id
            )
            
            session.add(position)
            session.commit()
            
            return position.position_id
            
        finally:
            session.close()
    
    async def add_dca_order(self, position_id: str, order_id: str, attempt_number: int,
                          side: str, quantity_requested: float, price_requested: Optional[float],
                          order_type: str, technical_context: Dict) -> str:
        """Add a new DCA order record."""
        session = self.db._session_factory()
        try:
            # Get current position state
            position = session.query(EnhancedPositionRecord).filter_by(position_id=position_id).first()
            if not position:
                raise ValueError(f"Position {position_id} not found")
            
            # Get last DCA price for progressive validation
            last_dca = session.query(DCAOrderRecord).filter_by(
                position_id=position_id
            ).order_by(DCAOrderRecord.dca_attempt_number.desc()).first()
            
            last_dca_price = last_dca.average_fill_price if last_dca and last_dca.average_fill_price else None
            
            dca_order = DCAOrderRecord(
                position_id=position_id,
                order_id=order_id,
                dca_attempt_number=attempt_number,
                side=side,
                quantity_requested=quantity_requested,
                price_requested=price_requested,
                order_type=order_type,
                technical_reason=technical_context.get('reason'),
                technical_level=technical_context.get('level'),
                technical_confidence=technical_context.get('confidence'),
                timeframe_used=technical_context.get('timeframe'),
                position_avg_before=position.current_avg_price,
                quantity_before=position.current_quantity,
                last_dca_price=last_dca_price,
                is_progressive=True  # Will be validated on fill
            )
            
            session.add(dca_order)
            session.commit()
            
            return dca_order.dca_order_id
            
        finally:
            session.close()
    
    async def update_dca_on_fill(self, order_id: str, quantity_filled: float, 
                               average_fill_price: float) -> bool:
        """Update DCA order when it fills."""
        session = self.db._session_factory()
        try:
            # Find the DCA order
            dca_order = session.query(DCAOrderRecord).filter_by(order_id=order_id).first()
            if not dca_order:
                return False
            
            # Update DCA order
            dca_order.status = 'filled' if quantity_filled >= dca_order.quantity_requested else 'partially_filled'
            dca_order.quantity_filled = quantity_filled
            dca_order.average_fill_price = average_fill_price
            dca_order.filled_at = datetime.utcnow()
            
            # Validate if progressive
            if dca_order.last_dca_price is not None:
                if dca_order.side.lower() == 'buy':
                    is_progressive = average_fill_price < dca_order.last_dca_price
                    improvement = ((dca_order.last_dca_price - average_fill_price) / dca_order.last_dca_price * 100)
                else:
                    is_progressive = average_fill_price > dca_order.last_dca_price
                    improvement = ((average_fill_price - dca_order.last_dca_price) / dca_order.last_dca_price * 100)
                
                dca_order.is_progressive = is_progressive
                dca_order.progression_improvement_pct = improvement if is_progressive else None
            
            # Update position
            position = session.query(EnhancedPositionRecord).filter_by(
                position_id=dca_order.position_id
            ).first()
            
            if position:
                # Calculate new average and quantity
                if dca_order.side.lower() == 'buy':
                    new_quantity = position.current_quantity + quantity_filled
                    total_cost = (position.current_quantity * position.current_avg_price) + (quantity_filled * average_fill_price)
                    new_avg_price = total_cost / new_quantity
                else:  # sell
                    new_quantity = position.current_quantity - quantity_filled
                    new_avg_price = position.current_avg_price  # Average doesn't change on sells
                
                position.current_quantity = new_quantity
                position.current_avg_price = new_avg_price
                position.total_dca_attempts += 1
                position.updated_at = datetime.utcnow()
                
                # Update DCA order with position impact
                dca_order.quantity_after = new_quantity
                dca_order.position_avg_after = new_avg_price
            
            session.commit()
            return True
            
        finally:
            session.close()

if __name__ == "__main__":
    print("Enhanced Database Schema for Transparent Position and DCA Tracking")
    print("Provides comprehensive visibility for localhost endpoints")
