"""
DCA Pause Guard

Gates DCA (Dollar Cost Averaging) attempts during critical resilience states.
Prevents averaging down when system is in degraded health states (CRITICAL, FAIL_CLOSED).

Key Behavior:
- Pauses DCA in CRITICAL and FAIL_CLOSED states
- Allows initial position entries regardless of resilience state
- Emits metrics for tracking pause events

Usage:
    guard = DcaPauseGuard(resilience_tracker)
    decision = await guard.evaluate()
    
    if not decision.allow_dca:
        logger.warning(f"DCA paused: {decision.reason}")
        return
"""

from dataclasses import dataclass
from typing import Optional

from src.core.logging_config import get_logger
from src.resilience.resilience_state_tracker import (
    ResilienceStateTracker,
    ResilienceState
)
from src.utils.metrics import dca_pause_events_total


logger = get_logger(__name__)


@dataclass(frozen=True)
class DcaPauseDecision:
    """Decision result for DCA pause evaluation.
    
    Attributes:
        allow_dca: Whether to allow DCA order execution
        reason: Optional explanation if DCA is paused
    """
    allow_dca: bool
    reason: Optional[str] = None


class DcaPauseGuard:
    """Guards DCA attempts based on system resilience state.
    
    Pauses DCA when system is in critical states to prevent
    compounding losses during system degradation.
    
    Attributes:
        tracker: ResilienceStateTracker instance
        pause_states: Set of states that trigger DCA pause
    """
    
    def __init__(
        self,
        tracker: ResilienceStateTracker,
        pause_states: Optional[set] = None
    ):
        """Initialize DCA pause guard.
        
        Args:
            tracker: ResilienceStateTracker for reading system state
            pause_states: States that trigger DCA pause (default: CRITICAL, FAIL_CLOSED)
        """
        self.tracker = tracker
        self.pause_states = pause_states or {
            ResilienceState.CRITICAL,
            ResilienceState.FAIL_CLOSED
        }
        
        logger.info(
            f"DcaPauseGuard initialized with pause states: "
            f"{[state.value for state in self.pause_states]}"
        )
    
    async def evaluate(self) -> DcaPauseDecision:
        """Evaluate whether to allow DCA based on current resilience state.
        
        Returns:
            DcaPauseDecision with allow_dca flag and optional reason
        """
        current_state = self.tracker.state
        
        if current_state in self.pause_states:
            reason = f"paused_due_to_state:{current_state.value}"
            
            # Emit metric for tracking
            dca_pause_events_total.labels(state=current_state.value).inc()
            
            logger.warning(
                f"🛑 DCA paused due to resilience state",
                extra={
                    "component": "DcaPauseGuard",
                    "state": current_state.value,
                    "pause_states": [s.value for s in self.pause_states]
                }
            )
            
            return DcaPauseDecision(allow_dca=False, reason=reason)
        
        logger.debug(
            f"✅ DCA allowed in state: {current_state.value}",
            extra={"component": "DcaPauseGuard", "state": current_state.value}
        )
        
        return DcaPauseDecision(allow_dca=True)
    
    def update_pause_states(self, pause_states: set) -> None:
        """Update the set of states that trigger DCA pause.
        
        Args:
            pause_states: New set of ResilienceState values
        """
        old_states = [s.value for s in self.pause_states]
        self.pause_states = pause_states
        new_states = [s.value for s in self.pause_states]
        
        logger.info(
            f"DCA pause states updated",
            extra={
                "component": "DcaPauseGuard",
                "old_states": old_states,
                "new_states": new_states
            }
        )
