"""
API Response Helpers

Centralized response formatting for FastAPI endpoints.
Eliminates duplicate JSONResponse patterns across the codebase.

Usage:
    from src.signals.response_helpers import success_response, error_response
    
    # Success response with data
    return success_response(data={"positions": positions})
    
    # Error response
    return error_response("Position not found", status_code=404)
    
    # Success with custom status
    return success_response(data={"id": new_id}, status_code=201)

Author: Trading Bot Team
Version: 1.0.0
"""

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi.responses import JSONResponse


def success_response(
    data: Optional[Dict[str, Any]] = None,
    message: Optional[str] = None,
    status_code: int = 200,
) -> JSONResponse:
    """
    Create a standardized success response.
    
    Args:
        data: Response payload data
        message: Optional success message
        status_code: HTTP status code (default: 200)
        
    Returns:
        JSONResponse with consistent structure:
        {
            "status": "success",
            "timestamp": "2024-01-01T00:00:00.000000",
            "data": {...},
            "message": "..." (optional)
        }
    """
    content: Dict[str, Any] = {
        "status": "success",
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    if data is not None:
        content["data"] = data
    
    if message is not None:
        content["message"] = message
    
    return JSONResponse(content=content, status_code=status_code)


def error_response(
    message: str,
    status_code: int = 500,
    error_code: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """
    Create a standardized error response.
    
    Args:
        message: Human-readable error message
        status_code: HTTP status code (default: 500)
        error_code: Machine-readable error code (optional)
        details: Additional error context (optional)
        
    Returns:
        JSONResponse with consistent structure:
        {
            "status": "error",
            "timestamp": "2024-01-01T00:00:00.000000",
            "message": "...",
            "error_code": "..." (optional),
            "details": {...} (optional)
        }
    """
    content: Dict[str, Any] = {
        "status": "error",
        "timestamp": datetime.utcnow().isoformat(),
        "message": message,
    }
    
    if error_code is not None:
        content["error_code"] = error_code
    
    if details is not None:
        content["details"] = details
    
    return JSONResponse(content=content, status_code=status_code)


def empty_data_response(
    data_key: str,
    empty_value: Any = None,
    message: Optional[str] = None,
) -> JSONResponse:
    """
    Create a response for empty/not-found data scenarios.
    
    Useful when data is not available but it's not an error.
    
    Args:
        data_key: Key name for the empty data (e.g., "positions", "orders")
        empty_value: Value for empty data (default: None, use [] for lists)
        message: Optional message explaining why data is empty
        
    Returns:
        JSONResponse with status "success" and empty data
    """
    data = {data_key: empty_value if empty_value is not None else []}
    return success_response(data=data, message=message)


def health_response(
    healthy: bool,
    checks: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """
    Create a standardized health check response.
    
    Args:
        healthy: Overall health status
        checks: Individual health check results
        
    Returns:
        JSONResponse with appropriate status code (200 or 503)
    """
    content: Dict[str, Any] = {
        "status": "healthy" if healthy else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    if checks is not None:
        content["checks"] = checks
    
    status_code = 200 if healthy else 503
    return JSONResponse(content=content, status_code=status_code)


# Convenience aliases for common patterns
def not_found_response(resource: str, identifier: Optional[str] = None) -> JSONResponse:
    """Create a 404 not found response."""
    message = f"{resource} not found"
    if identifier:
        message = f"{resource} '{identifier}' not found"
    return error_response(message, status_code=404, error_code="NOT_FOUND")


def validation_error_response(message: str, details: Optional[Dict[str, Any]] = None) -> JSONResponse:
    """Create a 422 validation error response."""
    return error_response(message, status_code=422, error_code="VALIDATION_ERROR", details=details)


def unauthorized_response(message: str = "Unauthorized access") -> JSONResponse:
    """Create a 401 unauthorized response."""
    return error_response(message, status_code=401, error_code="UNAUTHORIZED")


def forbidden_response(message: str = "Access forbidden") -> JSONResponse:
    """Create a 403 forbidden response."""
    return error_response(message, status_code=403, error_code="FORBIDDEN")
