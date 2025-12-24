"""
Configuration Router.

Handles configuration update operations:
- Get current configuration
- Update configuration
- Validate configuration

Author: Trading Bot Team
Version: 2.0.0
"""

from typing import Optional, Dict, Any

from pydantic import BaseModel, Field
from fastapi import Request, HTTPException, Header
from fastapi.responses import JSONResponse

from src.core.logging_config import get_logger
from src.constants import HTTPStatus
from src.signals.routers.base_router import BaseAdminRouter, handle_route_errors

# Config service import - may not exist in older installations
try:
    from src.services.config_service_interface import IConfigService
except ImportError:
    IConfigService = None  # type: ignore


logger = get_logger(__name__)


# =============================================================================
# Configuration Request/Response Models
# =============================================================================

class ConfigUpdateRequest(BaseModel):
    """Request model for configuration update."""
    section: str = Field(..., min_length=1, max_length=50)
    key: str = Field(..., min_length=1, max_length=100)
    value: Any = Field(...)
    description: Optional[str] = Field(None, max_length=200)


class BulkConfigUpdateRequest(BaseModel):
    """Request model for bulk configuration updates."""
    updates: Dict[str, Dict[str, Any]] = Field(...)
    
    class Config:
        schema_extra = {
            "example": {
                "updates": {
                    "trading": {
                        "max_position_size": 1000,
                        "risk_percent": 2.0
                    },
                    "risk": {
                        "stop_loss_percent": 5.0
                    }
                }
            }
        }


class ConfigRouter(BaseAdminRouter):
    """
    Router for configuration operations.
    
    Provides endpoints for:
    - GET /config - Get all configuration
    - GET /config/{section} - Get configuration section
    - PUT /config - Update single configuration
    - PUT /config/bulk - Bulk update configuration
    - POST /config/validate - Validate configuration
    """
    
    def __init__(
        self,
        config_service: Optional["IConfigService"] = None,
        auth_service=None,
        bot_instance=None
    ):
        """
        Initialize configuration router.
        
        Args:
            config_service: Configuration management service
            auth_service: Authentication service
            bot_instance: Legacy bot instance for backward compatibility
        """
        super().__init__(auth_service=auth_service, prefix="/admin", tags=["config"])
        
        self._config_service = config_service
        self._bot_instance = bot_instance
        
        self._setup_routes()
        logger.info("✅ ConfigRouter initialized")
    
    def set_config_service(self, config_service: "IConfigService") -> None:
        """Set the configuration service."""
        self._config_service = config_service
        logger.info("Config service set for ConfigRouter")
    
    def set_bot_instance(self, bot_instance) -> None:
        """Set legacy bot instance for backward compatibility."""
        self._bot_instance = bot_instance
    
    def _get_legacy_config(self) -> Dict[str, Any]:
        """Get configuration from legacy bot instance."""
        if not self._bot_instance:
            return {}
        
        config_manager = getattr(self._bot_instance, 'config_manager', None)
        if not config_manager:
            return {}
        
        return {
            "trading": {
                "symbol": getattr(config_manager, 'symbol', 'N/A'),
                "order_size": getattr(config_manager, 'order_size', 0),
            },
            "risk": {
                "max_position_risk": getattr(config_manager, 'max_position_risk', 0),
            },
            "dca": {
                "max_dca_levels": getattr(config_manager, 'max_dca_levels', 0),
                "dca_drop_percentage": getattr(config_manager, 'dca_drop_percentage', 0),
            }
        }
    
    async def _update_legacy_config(self, section: str, key: str, value: Any) -> bool:
        """Update configuration on legacy bot instance."""
        if not self._bot_instance:
            return False
        
        config_manager = getattr(self._bot_instance, 'config_manager', None)
        if not config_manager:
            return False
        
        # Map section.key to config attribute
        config_key = f"{section}_{key}" if section != "trading" else key
        if hasattr(config_manager, config_key):
            setattr(config_manager, config_key, value)
            return True
        
        return False
    
    def _setup_routes(self) -> None:
        """Setup configuration routes."""
        
        @self.router.get("/config")
        async def get_config(
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Get all configuration settings."""
            await self.validate_auth(request, authorization)
            
            # Try config service first
            if self._config_service:
                try:
                    config = await self._config_service.get_all_config()
                    return JSONResponse(content={"config": config})
                except Exception as e:
                    logger.error(f"Config service error: {e}")
            
            # Fall back to legacy bot instance
            config = self._get_legacy_config()
            return JSONResponse(content={"config": config})
        
        @self.router.get("/config/{section}")
        async def get_config_section(
            section: str,
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Get a specific configuration section."""
            await self.validate_auth(request, authorization)
            
            if self._config_service:
                try:
                    config = await self._config_service.get_section_config(section)
                    return JSONResponse(content={"section": section, "config": config})
                except Exception as e:
                    logger.error(f"Config service error: {e}")
            
            # Fall back to legacy
            full_config = self._get_legacy_config()
            section_config = full_config.get(section, {})
            return JSONResponse(content={"section": section, "config": section_config})
        
        @self.router.put("/config")
        @handle_route_errors(operation_name="update_config")
        async def update_config(
            config_request: ConfigUpdateRequest,
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Update a single configuration setting."""
            claims = await self.validate_auth(request, authorization)
            user_id = claims.user_id if claims else "anonymous"
            
            # Try config service first
            if self._config_service:
                updated = await self._config_service.update_config(
                    section=config_request.section,
                    key=config_request.key,
                    value=config_request.value,
                    user_id=user_id
                )
                
                if updated:
                    logger.info(
                        f"Config updated: {config_request.section}.{config_request.key} "
                        f"= {config_request.value} by {user_id}"
                    )
                    return JSONResponse(content={
                        "status": "updated",
                        "section": config_request.section,
                        "key": config_request.key,
                        "value": config_request.value
                    })
            
            # Try legacy bot instance
            if await self._update_legacy_config(
                config_request.section,
                config_request.key,
                config_request.value
            ):
                return JSONResponse(content={
                    "status": "updated",
                    "section": config_request.section,
                    "key": config_request.key,
                    "value": config_request.value
                })
            
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=f"Unknown configuration key: {config_request.section}.{config_request.key}"
            )
        
        @self.router.put("/config/bulk")
        @handle_route_errors(operation_name="bulk_update_config")
        async def bulk_update_config(
            bulk_request: BulkConfigUpdateRequest,
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Bulk update configuration settings."""
            claims = await self.validate_auth(request, authorization)
            user_id = claims.user_id if claims else "anonymous"
            
            if not self._config_service:
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_ERROR,
                    detail="Bulk update requires config service"
                )
            
            results = await self._config_service.bulk_update_config(
                updates=bulk_request.updates,
                user_id=user_id
            )
            
            logger.info(f"Bulk config update by {user_id}: {len(results)} sections")
            return JSONResponse(content={
                "status": "updated",
                "results": results
            })
        
        @self.router.post("/config/validate")
        @handle_route_errors(operation_name="validate_config")
        async def validate_config(
            bulk_request: BulkConfigUpdateRequest,
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Validate configuration without applying changes."""
            await self.validate_auth(request, authorization)
            
            if not self._config_service:
                return JSONResponse(content={
                    "valid": True,
                    "message": "Validation skipped - no config service"
                })
            
            validation_result = await self._config_service.validate_config(
                bulk_request.updates
            )
            return JSONResponse(content=validation_result)
