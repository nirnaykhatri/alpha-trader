"""
Startup Mode Configuration.

Defines the startup mode behavior for broker credential requirements.
This is the single source of truth for startup mode policy.

STARTUP MODES:
    The bot supports two startup modes controlled by STARTUP_MODE environment variable:
    
    - "headless" (default for production):
        Requires broker credentials at startup. Fail-fast if no broker configured.
        Use for production deployments where the bot should never run without a broker.
        
    - "ui-config" (default for development):
        Broker credentials are optional at startup. Users can add brokers via web UI.
        Use for development and demo environments where interactive setup is preferred.
    
    Set via environment: STARTUP_MODE=headless or STARTUP_MODE=ui-config

Usage:
    from src.core.startup_mode import StartupMode
    
    mode = StartupMode.from_env()
    if mode.requires_broker_at_startup:
        # Validate broker credentials
        ...
"""

import os
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class StartupMode(Enum):
    """
    Startup mode for broker credential requirements.
    
    This is the canonical source of truth for startup mode policy.
    All layers should depend on this class for startup mode decisions.
    
    Attributes:
        HEADLESS: Requires broker at startup (production mode).
        UI_CONFIG: Broker optional, can be added via UI (development mode).
    """
    HEADLESS = "headless"
    UI_CONFIG = "ui-config"
    
    @classmethod
    def from_env(cls) -> "StartupMode":
        """Get startup mode from STARTUP_MODE environment variable.
        
        Production Safety:
            - Defaults to HEADLESS in production (requires broker at startup)
            - Defaults to UI_CONFIG only when ENVIRONMENT=development
            - Explicit STARTUP_MODE always takes precedence
            
        Returns:
            StartupMode enum value
        """
        mode_str = os.environ.get("STARTUP_MODE", "").lower().strip()
        
        # Explicit mode takes precedence
        if mode_str == "headless":
            return cls.HEADLESS
        elif mode_str in ("ui-config", "ui_config", "uiconfig"):
            return cls.UI_CONFIG
        
        # No explicit mode - use environment-based default
        environment = os.environ.get("ENVIRONMENT", "production").lower().strip()
        if environment == "development":
            logger.info("STARTUP_MODE not set, defaulting to 'ui-config' (ENVIRONMENT=development)")
            return cls.UI_CONFIG
        else:
            logger.info("STARTUP_MODE not set, defaulting to 'headless' (production mode)")
            return cls.HEADLESS
    
    @property
    def requires_broker_at_startup(self) -> bool:
        """Whether broker credentials are required at startup.
        
        Returns:
            True if broker is required (HEADLESS mode), False otherwise.
        """
        return self == StartupMode.HEADLESS
    
    @property
    def allows_ui_broker_config(self) -> bool:
        """Whether brokers can be added via the web UI.
        
        Returns:
            True if UI configuration is allowed (UI_CONFIG mode), False otherwise.
        """
        return self == StartupMode.UI_CONFIG
