"""
Resilience State Tracker

Global system health monitoring with state transitions and automatic degradation management.
Aggregates signals from circuit breakers, queue saturation, provider health, and risk throttling
to determine overall system resilience state.

State Transitions:
    NORMAL → DEGRADED → CRITICAL → FAIL_CLOSED
    NORMAL → FAIL_OPEN (emergency bypass mode)

Usage:
    tracker = ResilienceStateTracker()
    await tracker.evaluate_system_health()
    
    if tracker.state == ResilienceState.CRITICAL:
        logger.critical("System in critical state, pausing new trades")
"""

import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

from src.core.logging_config import get_logger
from src.utils.metrics import Counter, Gauge


logger = get_logger(__name__)


class ResilienceState(Enum):
    """System resilience states with increasing severity."""
    
    NORMAL = "normal"              # All systems operational
    DEGRADED = "degraded"          # Warning thresholds breached, reduced capacity
    CRITICAL = "critical"          # Critical thresholds breached, minimal capacity
    FAIL_OPEN = "fail_open"        # Emergency mode: allow trades despite issues
    FAIL_CLOSED = "fail_closed"    # Emergency mode: block all trades


class DegradationReason(Enum):
    """Reasons for system degradation."""
    
    # Provider issues
    PROVIDER_CIRCUIT_OPEN = "provider_circuit_open"
    PROVIDER_LATENCY_HIGH = "provider_latency_high"
    PROVIDER_ERROR_RATE_HIGH = "provider_error_rate_high"
    
    # Queue saturation
    EVENT_QUEUE_SATURATED = "event_queue_saturated"
    ORDER_QUEUE_BACKLOG = "order_queue_backlog"
    
    # Risk throttling
    RISK_CIRCUIT_BREAKER_ACTIVE = "risk_circuit_breaker_active"
    DAILY_LOSS_LIMIT_APPROACHED = "daily_loss_limit_approached"
    
    # Resource exhaustion
    MEMORY_USAGE_HIGH = "memory_usage_high"
    CPU_USAGE_HIGH = "cpu_usage_high"
    DATABASE_CONNECTION_POOL_EXHAUSTED = "database_connection_pool_exhausted"
    
    # External dependencies
    BROKER_API_DEGRADED = "broker_api_degraded"
    MARKET_DATA_STALE = "market_data_stale"


@dataclass
class DegradationEvent:
    """Record of a degradation event."""
    
    reason: DegradationReason
    severity: str  # "warning" | "critical"
    timestamp: datetime
    details: Dict[str, any] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    
    def __str__(self) -> str:
        status = "RESOLVED" if self.resolved else "ACTIVE"
        return f"[{status}] {self.reason.value} ({self.severity}) - {self.details}"


class ResilienceStateTracker:
    """
    Tracks global system resilience state and manages degradation transitions.
    
    Monitors:
    - Circuit breaker states (market data providers, broker API)
    - Event queue saturation levels
    - Risk circuit breaker activations
    - Resource utilization (memory, CPU, DB connections)
    - Provider health metrics
    
    Automatically transitions between states based on aggregated health signals.
    Publishes state transitions as metrics and events for observability.
    """
    
    # State transition thresholds
    DEGRADED_THRESHOLD = 2      # Number of active degradation reasons to trigger DEGRADED
    CRITICAL_THRESHOLD = 4      # Number of active degradation reasons to trigger CRITICAL
    
    # Severity weights
    WARNING_WEIGHT = 1
    CRITICAL_WEIGHT = 3
    
    def __init__(self, 
                 evaluation_interval: int = 30,
                 state_change_cooldown: int = 60):
        """
        Initialize resilience state tracker.
        
        Args:
            evaluation_interval: Seconds between health evaluations
            state_change_cooldown: Minimum seconds between state transitions
        """
        self.state = ResilienceState.NORMAL
        self.previous_state = ResilienceState.NORMAL
        self.state_changed_at = datetime.utcnow()
        
        self.evaluation_interval = evaluation_interval
        self.state_change_cooldown = timedelta(seconds=state_change_cooldown)
        
        # Track active degradation reasons
        self.active_degradations: Dict[DegradationReason, DegradationEvent] = {}
        self.degradation_history: List[DegradationEvent] = []
        
        # Track circuit breaker states
        self.circuit_breakers: Dict[str, str] = {}  # name -> state (open/closed/half_open)
        
        # Metrics
        self._init_metrics()
        
        # Background evaluation task
        self._evaluation_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(
            f"ResilienceStateTracker initialized "
            f"(eval_interval={evaluation_interval}s, cooldown={state_change_cooldown}s)"
        )
    
    def _init_metrics(self):
        """Initialize Prometheus metrics."""
        self.state_gauge = Gauge(
            'trading_bot_resilience_state',
            'Current resilience state (0=NORMAL, 1=DEGRADED, 2=CRITICAL, 3=FAIL_OPEN, 4=FAIL_CLOSED)',
            []
        )
        
        self.state_transitions_total = Counter(
            'trading_bot_resilience_state_transitions_total',
            'Total state transitions',
            ['from_state', 'to_state']
        )
        
        self.active_degradations_gauge = Gauge(
            'trading_bot_active_degradations',
            'Number of active degradation reasons',
            []
        )
        
        self.degradation_events_total = Counter(
            'trading_bot_degradation_events_total',
            'Total degradation events',
            ['reason', 'severity']
        )
    
    async def start(self):
        """Start background health evaluation loop."""
        if self._running:
            logger.warning("ResilienceStateTracker already running")
            return
        
        self._running = True
        self._evaluation_task = asyncio.create_task(self._evaluation_loop())
        logger.info("ResilienceStateTracker started")
    
    async def stop(self):
        """Stop background health evaluation loop."""
        if not self._running:
            return
        
        self._running = False
        if self._evaluation_task:
            self._evaluation_task.cancel()
            try:
                await self._evaluation_task
            except asyncio.CancelledError:
                pass
        
        logger.info("ResilienceStateTracker stopped")
    
    async def _evaluation_loop(self):
        """Background loop for periodic health evaluation."""
        while self._running:
            try:
                await self.evaluate_system_health()
                await asyncio.sleep(self.evaluation_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in resilience evaluation loop: {e}", exc_info=True)
                await asyncio.sleep(self.evaluation_interval)
    
    async def evaluate_system_health(self) -> ResilienceState:
        """
        Evaluate overall system health and determine resilience state.
        
        Returns:
            Current resilience state after evaluation
        """
        # Calculate degradation score
        score = self._calculate_degradation_score()
        
        # Determine target state
        new_state = self._determine_state(score)
        
        # Apply state transition with cooldown
        if new_state != self.state:
            await self._transition_state(new_state)
        
        # Update metrics
        self._update_metrics()
        
        return self.state
    
    def _calculate_degradation_score(self) -> int:
        """
        Calculate weighted degradation score from active degradations.
        
        Returns:
            Degradation score (higher = worse health)
        """
        score = 0
        
        for degradation in self.active_degradations.values():
            if degradation.severity == "critical":
                score += self.CRITICAL_WEIGHT
            else:  # warning
                score += self.WARNING_WEIGHT
        
        return score
    
    def _determine_state(self, degradation_score: int) -> ResilienceState:
        """
        Determine target resilience state based on degradation score.
        
        Args:
            degradation_score: Weighted degradation score
        
        Returns:
            Target resilience state
        """
        # Check for manual overrides first
        if hasattr(self, '_manual_state_override'):
            return self._manual_state_override
        
        # State determination logic
        if degradation_score == 0:
            return ResilienceState.NORMAL
        elif degradation_score < self.DEGRADED_THRESHOLD * self.CRITICAL_WEIGHT:
            return ResilienceState.DEGRADED
        elif degradation_score < self.CRITICAL_THRESHOLD * self.CRITICAL_WEIGHT:
            return ResilienceState.CRITICAL
        else:
            # Default to FAIL_CLOSED for extreme degradation
            return ResilienceState.FAIL_CLOSED
    
    async def _transition_state(self, new_state: ResilienceState):
        """
        Transition to a new resilience state with cooldown enforcement.
        
        Args:
            new_state: Target resilience state
        """
        now = datetime.utcnow()
        
        # Enforce cooldown (except for emergency transitions)
        if (new_state not in [ResilienceState.FAIL_OPEN, ResilienceState.FAIL_CLOSED] and
            now - self.state_changed_at < self.state_change_cooldown):
            logger.debug(
                f"State transition to {new_state.value} delayed by cooldown "
                f"({(self.state_change_cooldown - (now - self.state_changed_at)).total_seconds():.0f}s remaining)"
            )
            return
        
        # Log transition
        logger.warning(
            f"🔄 Resilience state transition: {self.state.value} → {new_state.value}",
            extra={
                'component': 'ResilienceStateTracker',
                'from_state': self.state.value,
                'to_state': new_state.value,
                'active_degradations': len(self.active_degradations),
                'degradation_reasons': [d.reason.value for d in self.active_degradations.values()]
            }
        )
        
        # Update state
        self.previous_state = self.state
        self.state = new_state
        self.state_changed_at = now
        
        # Update metrics
        self.state_transitions_total.labels(
            from_state=self.previous_state.value,
            to_state=new_state.value
        ).inc()
        
        # Emit event (if event bus available)
        await self._emit_state_change_event()
    
    async def _emit_state_change_event(self):
        """Emit state change event to event bus (if available)."""
        try:
            from src.events.event_bus import EventBus, EventPriority
            
            event_bus = EventBus()
            await event_bus.publish(
                event_type="resilience_state_changed",
                priority=EventPriority.HIGH if self.state in [ResilienceState.CRITICAL, ResilienceState.FAIL_CLOSED] else EventPriority.NORMAL,
                payload={
                    'from_state': self.previous_state.value,
                    'to_state': self.state.value,
                    'active_degradations': len(self.active_degradations),
                    'timestamp': datetime.utcnow()
                }
            )
        except Exception as e:
            logger.debug(f"Could not emit state change event: {e}")
    
    def _update_metrics(self):
        """Update Prometheus metrics."""
        # Map state to numeric value
        state_values = {
            ResilienceState.NORMAL: 0,
            ResilienceState.DEGRADED: 1,
            ResilienceState.CRITICAL: 2,
            ResilienceState.FAIL_OPEN: 3,
            ResilienceState.FAIL_CLOSED: 4,
        }
        
        self.state_gauge.set(state_values[self.state])
        self.active_degradations_gauge.set(len(self.active_degradations))
    
    def report_degradation(self,
                          reason: DegradationReason,
                          severity: str = "warning",
                          details: Optional[Dict] = None):
        """
        Report a new degradation event.
        
        Args:
            reason: Degradation reason
            severity: Severity level ("warning" or "critical")
            details: Additional context
        """
        if reason in self.active_degradations:
            # Update existing degradation
            self.active_degradations[reason].details.update(details or {})
            return
        
        # Create new degradation event
        event = DegradationEvent(
            reason=reason,
            severity=severity,
            timestamp=datetime.utcnow(),
            details=details or {}
        )
        
        self.active_degradations[reason] = event
        self.degradation_history.append(event)
        
        # Update metrics
        self.degradation_events_total.labels(
            reason=reason.value,
            severity=severity
        ).inc()
        
        logger.warning(
            f"⚠️ Degradation reported: {event}",
            extra={'component': 'ResilienceStateTracker'}
        )
    
    def resolve_degradation(self, reason: DegradationReason):
        """
        Mark a degradation as resolved.
        
        Args:
            reason: Degradation reason to resolve
        """
        if reason not in self.active_degradations:
            return
        
        event = self.active_degradations[reason]
        event.resolved = True
        event.resolved_at = datetime.utcnow()
        
        del self.active_degradations[reason]
        
        logger.info(
            f"✅ Degradation resolved: {reason.value}",
            extra={
                'component': 'ResilienceStateTracker',
                'duration_seconds': (event.resolved_at - event.timestamp).total_seconds()
            }
        )
    
    def register_circuit_breaker(self, name: str, state: str):
        """
        Register circuit breaker state.
        
        Args:
            name: Circuit breaker name (e.g., "polygon_provider")
            state: State ("open", "closed", "half_open")
        """
        prev_state = self.circuit_breakers.get(name)
        self.circuit_breakers[name] = state
        
        # Auto-report degradation for open circuit breakers
        if state == "open" and prev_state != "open":
            self.report_degradation(
                DegradationReason.PROVIDER_CIRCUIT_OPEN,
                severity="warning",
                details={'circuit_breaker': name}
            )
        elif state in ["closed", "half_open"] and prev_state == "open":
            # Resolve if moving away from open state
            self.resolve_degradation(DegradationReason.PROVIDER_CIRCUIT_OPEN)
    
    def set_manual_override(self, state: Optional[ResilienceState] = None):
        """
        Manually override resilience state (for emergency operations).
        
        Args:
            state: Target state (None to clear override)
        """
        if state is None:
            if hasattr(self, '_manual_state_override'):
                delattr(self, '_manual_state_override')
                logger.warning("Manual state override cleared")
        else:
            self._manual_state_override = state
            logger.critical(
                f"🚨 Manual state override: {state.value}",
                extra={'component': 'ResilienceStateTracker'}
            )
    
    def get_status(self) -> Dict:
        """
        Get current resilience status.
        
        Returns:
            Status dictionary with state, degradations, and circuit breakers
        """
        return {
            'state': self.state.value,
            'previous_state': self.previous_state.value,
            'state_changed_at': self.state_changed_at.isoformat(),
            'active_degradations': [
                {
                    'reason': d.reason.value,
                    'severity': d.severity,
                    'timestamp': d.timestamp.isoformat(),
                    'details': d.details
                }
                for d in self.active_degradations.values()
            ],
            'circuit_breakers': self.circuit_breakers,
            'degradation_score': self._calculate_degradation_score(),
            'manual_override': hasattr(self, '_manual_state_override')
        }


# Singleton instance
_tracker_instance: Optional[ResilienceStateTracker] = None


def get_resilience_tracker() -> ResilienceStateTracker:
    """
    Get singleton ResilienceStateTracker instance.
    
    Returns:
        Global ResilienceStateTracker instance
    """
    global _tracker_instance
    
    if _tracker_instance is None:
        _tracker_instance = ResilienceStateTracker()
    
    return _tracker_instance
