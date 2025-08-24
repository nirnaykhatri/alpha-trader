"""
Database View Manager for Enhanced Position and DCA Tracking
Provides optimized database views and summary methods for localhost endpoint transparency.
"""

from sqlalchemy import func, text, case
from sqlalchemy.orm import Session, sessionmaker
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class PositionSummaryView:
    """
    Database view manager providing optimized queries for position and DCA summaries.
    """
    
    @staticmethod
    def get_position_summary(session: Session, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get comprehensive position summary with DCA details.
        
        This provides the core data for the /api/v2/positions endpoint with complete transparency.
        """
        try:
            from ..database.enhanced_schema import EnhancedPositionRecord, DCAOrderRecord
            
            # Base query for positions with DCA aggregation
            query = session.query(
                EnhancedPositionRecord,
                func.count(DCAOrderRecord.order_id).label('total_dca_orders'),
                func.count(case([(DCAOrderRecord.status == 'filled', DCAOrderRecord.order_id)])).label('filled_dca_orders'),
                func.count(case([(DCAOrderRecord.status == 'pending', DCAOrderRecord.order_id)])).label('pending_dca_orders'),
                func.count(case([(DCAOrderRecord.is_progressive == True, DCAOrderRecord.order_id)])).label('progressive_dca_orders'),
                func.avg(case([(DCAOrderRecord.status == 'filled', DCAOrderRecord.progression_improvement_pct)])).label('avg_improvement_pct'),
                func.max(DCAOrderRecord.average_fill_price).label('highest_dca_price'),
                func.min(DCAOrderRecord.average_fill_price).label('lowest_dca_price'),
                func.sum(case([(DCAOrderRecord.status == 'filled', DCAOrderRecord.quantity_filled * DCAOrderRecord.average_fill_price)])).label('total_dca_value')
            ).outerjoin(
                DCAOrderRecord, EnhancedPositionRecord.position_id == DCAOrderRecord.position_id
            ).filter(
                EnhancedPositionRecord.status == 'active'
            )
            
            if symbol:
                query = query.filter(EnhancedPositionRecord.symbol == symbol.upper())
            
            query = query.group_by(EnhancedPositionRecord.position_id)
            
            results = query.all()
            
            # Transform to API format
            position_summaries = []
            for result in results:
                position = result[0]  # EnhancedPositionRecord
                
                # Extract aggregated DCA data
                total_dca_orders = result.total_dca_orders or 0
                filled_dca_orders = result.filled_dca_orders or 0
                pending_dca_orders = result.pending_dca_orders or 0
                progressive_dca_orders = result.progressive_dca_orders or 0
                avg_improvement_pct = result.avg_improvement_pct or 0
                highest_dca_price = result.highest_dca_price
                lowest_dca_price = result.lowest_dca_price
                total_dca_value = result.total_dca_value or 0
                
                # Calculate current market value and P&L
                current_market_value = position.current_quantity * position.current_market_price
                unrealized_pnl = current_market_value - position.total_invested
                unrealized_pnl_percent = (unrealized_pnl / position.total_invested * 100) if position.total_invested > 0 else 0
                
                position_summary = {
                    'position_id': position.position_id,
                    'symbol': position.symbol,
                    'direction': position.direction,
                    'status': position.status,
                    'created_at': position.created_at.isoformat() if position.created_at else None,
                    'updated_at': position.updated_at.isoformat() if position.updated_at else None,
                    
                    'current': {
                        'quantity': position.current_quantity,
                        'average_price': position.average_price,
                        'market_price': position.current_market_price,
                        'market_value': current_market_value,
                        'cost_basis': position.total_invested
                    },
                    
                    'pnl': {
                        'unrealized': unrealized_pnl,
                        'unrealized_percent': unrealized_pnl_percent,
                        'daily_change': 0,  # Would require historical price data
                        'daily_change_percent': 0
                    },
                    
                    'dca_details': {
                        'total_attempts': total_dca_orders,
                        'filled_attempts': filled_dca_orders,
                        'pending_attempts': pending_dca_orders,
                        'progressive_attempts': progressive_dca_orders,
                        'progressive_rate': (progressive_dca_orders / filled_dca_orders * 100) if filled_dca_orders > 0 else 0,
                        'average_improvement_percent': float(avg_improvement_pct) if avg_improvement_pct else 0,
                        'price_range': {
                            'highest': float(highest_dca_price) if highest_dca_price else None,
                            'lowest': float(lowest_dca_price) if lowest_dca_price else None,
                            'spread_percent': ((highest_dca_price - lowest_dca_price) / lowest_dca_price * 100) if highest_dca_price and lowest_dca_price and lowest_dca_price > 0 else 0
                        },
                        'total_dca_value': float(total_dca_value) if total_dca_value else 0,
                        'dca_contribution_percent': (total_dca_value / position.total_invested * 100) if position.total_invested > 0 and total_dca_value else 0
                    },
                    
                    'risk_metrics': {
                        'position_age_hours': (datetime.utcnow() - position.created_at).total_seconds() / 3600 if position.created_at else 0,
                        'last_dca_age_minutes': 0,  # Would require additional query
                        'exposure_level': 'moderate',  # Would require portfolio context
                        'volatility_risk': 'medium'  # Would require historical analysis
                    },
                    
                    'technical_context': {
                        'entry_reason': position.entry_reason,
                        'strategy_used': position.strategy_used,
                        'timeframe': position.timeframe_used,
                        'confidence_level': position.confidence_level
                    }
                }
                
                position_summaries.append(position_summary)
            
            return position_summaries
            
        except Exception as e:
            logger.error(f"Error in get_position_summary: {e}")
            raise
    
    @staticmethod
    def get_dca_order_details(session: Session, position_id: str) -> List[Dict[str, Any]]:
        """
        Get detailed DCA order information for a specific position.
        """
        try:
            from ..database.enhanced_schema import DCAOrderRecord
            
            dca_orders = session.query(DCAOrderRecord).filter_by(
                position_id=position_id
            ).order_by(DCAOrderRecord.dca_attempt_number).all()
            
            return [order.to_api_dict() for order in dca_orders]
            
        except Exception as e:
            logger.error(f"Error in get_dca_order_details: {e}")
            raise
    
    @staticmethod
    def get_portfolio_metrics(session: Session) -> Dict[str, Any]:
        """
        Get comprehensive portfolio-level metrics and analytics.
        """
        try:
            from ..database.enhanced_schema import EnhancedPositionRecord, DCAOrderRecord
            
            # Portfolio overview query
            portfolio_query = session.query(
                func.count(EnhancedPositionRecord.position_id).label('total_positions'),
                func.count(func.distinct(EnhancedPositionRecord.symbol)).label('unique_symbols'),
                func.sum(EnhancedPositionRecord.total_invested).label('total_invested'),
                func.sum(EnhancedPositionRecord.current_quantity * EnhancedPositionRecord.current_market_price).label('total_market_value'),
                func.sum(EnhancedPositionRecord.unrealized_pnl).label('total_unrealized_pnl'),
                func.count(case([(EnhancedPositionRecord.unrealized_pnl > 0, EnhancedPositionRecord.position_id)])).label('positions_in_profit'),
                func.count(case([(EnhancedPositionRecord.unrealized_pnl < 0, EnhancedPositionRecord.position_id)])).label('positions_in_loss'),
                func.max(EnhancedPositionRecord.unrealized_pnl).label('max_single_gain'),
                func.min(EnhancedPositionRecord.unrealized_pnl).label('max_single_loss')
            ).filter(EnhancedPositionRecord.status == 'active').first()
            
            # DCA effectiveness query
            dca_query = session.query(
                func.count(DCAOrderRecord.order_id).label('total_dca_orders'),
                func.count(case([(DCAOrderRecord.status == 'filled', DCAOrderRecord.order_id)])).label('filled_dca_orders'),
                func.count(case([(DCAOrderRecord.is_progressive == True, DCAOrderRecord.order_id)])).label('progressive_dca_orders'),
                func.avg(case([(DCAOrderRecord.status == 'filled', DCAOrderRecord.progression_improvement_pct)])).label('avg_improvement_pct'),
                func.count(func.distinct(DCAOrderRecord.position_id)).label('positions_using_dca')
            ).join(EnhancedPositionRecord).filter(EnhancedPositionRecord.status == 'active').first()
            
            # Build metrics response
            total_invested = float(portfolio_query.total_invested or 0)
            total_market_value = float(portfolio_query.total_market_value or 0)
            total_unrealized_pnl = float(portfolio_query.total_unrealized_pnl or 0)
            
            filled_dca_orders = dca_query.filled_dca_orders or 0
            progressive_dca_orders = dca_query.progressive_dca_orders or 0
            
            metrics = {
                'portfolio_overview': {
                    'total_positions': portfolio_query.total_positions or 0,
                    'unique_symbols': portfolio_query.unique_symbols or 0,
                    'total_invested': total_invested,
                    'total_market_value': total_market_value,
                    'total_unrealized_pnl': total_unrealized_pnl,
                    'total_unrealized_pnl_percent': (total_unrealized_pnl / total_invested * 100) if total_invested > 0 else 0,
                    'positions_in_profit': portfolio_query.positions_in_profit or 0,
                    'positions_in_loss': portfolio_query.positions_in_loss or 0,
                    'max_single_gain': float(portfolio_query.max_single_gain or 0),
                    'max_single_loss': float(portfolio_query.max_single_loss or 0)
                },
                
                'dca_effectiveness': {
                    'total_dca_orders': dca_query.total_dca_orders or 0,
                    'filled_dca_orders': filled_dca_orders,
                    'progressive_dca_orders': progressive_dca_orders,
                    'progressive_percentage': (progressive_dca_orders / filled_dca_orders * 100) if filled_dca_orders > 0 else 0,
                    'average_improvement_percent': float(dca_query.avg_improvement_pct or 0),
                    'positions_using_dca': dca_query.positions_using_dca or 0,
                    'dca_adoption_rate': ((dca_query.positions_using_dca or 0) / (portfolio_query.total_positions or 1) * 100) if portfolio_query.total_positions else 0
                },
                
                'risk_analysis': {
                    'portfolio_concentration': 0,  # Would require additional query for largest position
                    'average_position_size': total_invested / (portfolio_query.total_positions or 1) if portfolio_query.total_positions else 0,
                    'profit_loss_ratio': (portfolio_query.positions_in_profit or 0) / (portfolio_query.positions_in_loss or 1) if portfolio_query.positions_in_loss else float('inf'),
                    'portfolio_diversification_score': min(portfolio_query.unique_symbols or 0, 10) * 10  # Simple diversification score
                },
                
                'performance_trends': {
                    'last_24h_pnl_change': 0,  # Would require historical data
                    'last_7d_pnl_change': 0,   # Would require historical data
                    'best_performing_symbol': None,  # Would require additional query
                    'worst_performing_symbol': None  # Would require additional query
                }
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error in get_portfolio_metrics: {e}")
            raise
    
    @staticmethod
    def get_recent_dca_activity(session: Session, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get recent DCA activity for dashboard visibility.
        """
        try:
            from ..database.enhanced_schema import DCAOrderRecord, EnhancedPositionRecord
            
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            
            recent_dcas = session.query(
                DCAOrderRecord,
                EnhancedPositionRecord.symbol
            ).join(
                EnhancedPositionRecord, DCAOrderRecord.position_id == EnhancedPositionRecord.position_id
            ).filter(
                DCAOrderRecord.placed_at >= cutoff_time
            ).order_by(
                DCAOrderRecord.placed_at.desc()
            ).limit(50).all()
            
            activity_list = []
            for dca_order, symbol in recent_dcas:
                activity = {
                    'timestamp': dca_order.placed_at.isoformat(),
                    'symbol': symbol,
                    'order_id': dca_order.order_id,
                    'dca_attempt': dca_order.dca_attempt_number,
                    'status': dca_order.status,
                    'price_requested': dca_order.price_requested,
                    'price_filled': dca_order.average_fill_price,
                    'quantity': dca_order.quantity_requested,
                    'quantity_filled': dca_order.quantity_filled,
                    'is_progressive': dca_order.is_progressive,
                    'improvement_percent': dca_order.progression_improvement_pct,
                    'technical_reason': dca_order.technical_reason,
                    'age_minutes': (datetime.utcnow() - dca_order.placed_at).total_seconds() / 60
                }
                activity_list.append(activity)
            
            return activity_list
            
        except Exception as e:
            logger.error(f"Error in get_recent_dca_activity: {e}")
            raise

# Example usage and testing
if __name__ == "__main__":
    print("Database View Manager for Enhanced Position and DCA Tracking")
    print("Provides optimized database queries for localhost endpoint transparency")
