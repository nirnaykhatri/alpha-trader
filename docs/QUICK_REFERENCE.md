# Quick Reference Guide - Code Improvements

## For Developers: How to Use New Features

### 1. Constants - Replace Magic Numbers

**Before:**
```python
timeout = 5.0
status_code = 403
max_retries = 3
```

**After:**
```python
from src.constants import APIConstants, HTTPStatus

timeout = APIConstants.DEFAULT_TIMEOUT
status_code = HTTPStatus.FORBIDDEN
max_retries = APIConstants.MAX_RETRY_ATTEMPTS
```

### 2. Decorators - Reduce Boilerplate

#### Localhost-Only Access
**Before:**
```python
@app.get("/admin")
async def admin_endpoint(request: Request):
    client_host = request.client.host if request.client else "unknown"
    if client_host not in ["127.0.0.1", "localhost", "::1"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    # ... actual logic
```

**After:**
```python
from src.utils.decorators import localhost_only

@app.get("/admin")
@localhost_only
async def admin_endpoint(request: Request):
    # ... actual logic (security handled by decorator)
```

#### Error Handling with Retries
**Before:**
```python
async def fetch_data(symbol: str):
    for attempt in range(3):
        try:
            return await api.get(symbol)
        except Exception as e:
            if attempt == 2:
                raise
            await asyncio.sleep(2 ** attempt)
```

**After:**
```python
from src.utils.decorators import handle_api_errors

@handle_api_errors(retryable=True, max_retries=3)
async def fetch_data(symbol: str):
    return await api.get(symbol)
```

#### Performance Monitoring
```python
from src.utils.decorators import log_execution_time

@log_execution_time
async def complex_operation():
    # Execution time automatically logged
    pass
```

### 3. Configuration Validation

**Validate YAML Config:**
```python
from src.core.pydantic_config import ConfigValidator
import yaml

# Configuration is now in TOML format
# See config/settings.toml for structure
    config_dict = yaml.safe_load(f)

# Validate and get type-safe settings
try:
    settings = ConfigValidator.validate_config_dict(config_dict)
    print(f"✅ Configuration valid - Using {settings.environment} environment")
    
    if settings.is_paper_trading():
        print("⚠️  Paper trading mode")
        
except ValueError as e:
    print(f"❌ Configuration error: {e}")
```

### 4. Database Connection Best Practices

**Connection pooling is now automatic!**

Just ensure your `settings.toml` has:
```yaml
database:
  url: "postgresql://user:pass@localhost/dbname"
  pool_size: 20        # Uses DatabaseConstants.POOL_SIZE if not specified
  max_overflow: 40     # Uses DatabaseConstants.POOL_MAX_OVERFLOW if not specified
  pool_timeout: 30
  pool_recycle: 3600
```

### 5. FastAPI Documentation

Access your API documentation:
- **Swagger UI:** http://localhost:8080/docs
- **ReDoc:** http://localhost:8080/redoc
- **OpenAPI JSON:** http://localhost:8080/openapi.json

## Common Patterns

### Pattern 1: Protected Admin Endpoint
```python
from src.utils.decorators import localhost_only, log_execution_time
from src.constants import HTTPStatus

@app.post("/admin/action")
@localhost_only
@log_execution_time
async def admin_action(request: Request):
    try:
        # Your logic here
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_ERROR,
            detail=str(e)
        )
```

### Pattern 2: API Call with Retry Logic
```python
from src.utils.decorators import handle_api_errors
from src.constants import APIConstants

@handle_api_errors(
    retryable=True,
    max_retries=APIConstants.MAX_RETRY_ATTEMPTS
)
async def call_external_api(symbol: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api.example.com/{symbol}",
            timeout=APIConstants.DEFAULT_TIMEOUT
        ) as response:
            return await response.json()
```

### Pattern 3: Rate Limited Function
```python
from src.utils.decorators import rate_limit
from src.constants import SecurityConstants

@rate_limit(calls_per_minute=SecurityConstants.MAX_REQUESTS_PER_MINUTE)
async def expensive_operation():
    # Automatically rate-limited
    pass
```

## Testing Tips

### Testing with Constants
```python
from src.constants import TradingConstants

def test_position_size():
    # Easy to reference standard values
    assert calculate_position_size() <= TradingConstants.MAX_POSITION_SIZE_PCT
```

### Testing Decorated Functions
```python
# Test the underlying function without decorator
from src.signals.signal_listener import TradingViewSignalListener

# Or mock the decorator
import unittest.mock as mock

with mock.patch('src.utils.decorators.localhost_only', lambda f: f):
    # Test without security check
    response = await endpoint(request)
```

## Migration Checklist

When adding new code, ensure you:

- [ ] Use constants instead of magic numbers
- [ ] Apply `@localhost_only` to admin endpoints
- [ ] Use `@handle_api_errors` for external API calls
- [ ] Import from `src.constants` instead of hardcoding
- [ ] Validate configuration with Pydantic models
- [ ] Add OpenAPI tags to new endpoints
- [ ] Use `HTTPStatus` constants for status codes
- [ ] Apply `@log_execution_time` to slow operations

## Performance Considerations

### Database Connection Pooling
- Pool size: 20 connections (configurable)
- Max overflow: 40 additional connections
- Auto-recycle: Every 3600 seconds
- Health check: `pool_pre_ping=True`

### Caching
```python
from src.constants import TimeConstants

# Use standard cache TTLs
cache_ttl = TimeConstants.CACHE_TTL_SHORT  # 60 seconds
cache_ttl = TimeConstants.CACHE_TTL_MEDIUM  # 300 seconds
cache_ttl = TimeConstants.CACHE_TTL_LONG  # 3600 seconds
```

## Troubleshooting

### "Configuration validation failed"
Check your config against Pydantic models in `src/core/pydantic_config.py`:
```python
from src.core.pydantic_config import TradingBotSettings

try:
    settings = TradingBotSettings(**config_dict)
except Exception as e:
    print(f"Invalid config: {e}")
```

### "Import error for decorators"
Ensure `src/utils/decorators.py` exists and has all required imports.

### "Constant not found"
Check if you're using the right constant class:
- API-related: `APIConstants`
- HTTP codes: `HTTPStatus`
- Trading: `TradingConstants`
- Database: `DatabaseConstants`
- Time: `TimeConstants`
- Security: `SecurityConstants`

## Additional Resources

- **Full Implementation Details:** See `IMPLEMENTATION_SUMMARY.md`
- **Original Code Review:** See `code-review.md`
- **Constants Reference:** `src/constants.py` (fully documented)
- **Decorator Reference:** `src/utils/decorators.py` (with examples)
- **Config Models:** `src/core/pydantic_config.py` (with validation rules)

---

**Last Updated:** October 2, 2025  
**Version:** 1.0.0
