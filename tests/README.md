# Testing Documentation

This document describes the testing strategy and organization for the Trading Bot webhook handling system.

## Test Organization

### Test Structure
```
tests/
├── test_webhook_concurrency.py      # Main webhook concurrency tests (pytest)
├── test_webhook_handler_async.py    # Advanced async webhook tests
├── test_config.py                   # Test configuration and utilities
├── run_webhook_tests.py             # Comprehensive test runner
├── unit/                            # Unit tests for individual components
├── integration/                     # Integration tests for workflows
└── fixtures/                        # Test data and fixtures
```

## Webhook Tests

### Quick Test Commands

```bash
# Run all webhook tests
python -m pytest tests/test_webhook_concurrency.py -v

# Run specific test
python -m pytest tests/test_webhook_concurrency.py::TestWebhookConcurrency::test_webhook_concurrent_requests -v

# Run with automatic URL detection
python tests/run_webhook_tests.py

# Run with specific URL (Azure deployment or local ngrok)
python tests/run_webhook_tests.py https://your-app.azurecontainerapps.io/webhook
```

### Test Categories

#### 1. Concurrency Tests (`test_webhook_concurrency.py`)
- **Single Request Test**: Verifies basic webhook functionality
- **Concurrent Requests Test**: Tests multiple simultaneous requests
- **Rapid Succession Test**: Tests rapid sequential requests
- **Different Payloads Test**: Tests various signal types

**Key Assertions**:
- All responses < 2 seconds
- All requests succeed
- All responses contain valid signal IDs
- No request blocking occurs

#### 2. Async Handler Tests (`test_webhook_handler_async.py`) 
- **Fire-and-Forget Test**: Verifies webhook responds before callback completes
- **Slow Callback Test**: Tests with deliberately slow callbacks (2+ seconds)
- **Failing Callback Test**: Tests webhook behavior when callbacks fail
- **Signal Processing Timeout**: Tests timeout handling for malformed requests

**Key Assertions**:
- Webhook responds in < 1 second even with 5-second callbacks
- Callback failures don't affect webhook responses
- Multiple concurrent requests work with slow processing
- Proper error handling for invalid requests

### Test Configuration

#### Environment Detection
The test runner automatically detects your webhook URL by testing:
1. `http://localhost:8080/webhook` (default local)
2. Environment variable `WEBHOOK_URL`
3. Health endpoint verification

#### Test Payloads
Predefined test payloads in `test_config.py`:
- **valid_buy**: Standard buy signal
- **valid_sell**: Standard sell signal  
- **short_sell_fail**: Triggers "cannot be sold short" error (for testing retry logic)
- **invalid**: Malformed payload for error testing

### Manual Testing

#### PowerShell Testing
```powershell
# Test the actual fix scenario
$payload = '{"symbol":"RGTI","action":"sell","price":13.48,"quantity":148}'

# For Azure deployment (recommended):
Invoke-RestMethod -Uri "https://your-app.azurecontainerapps.io/webhook" -Method POST -Headers @{"Content-Type"="application/json"} -Body $payload

# For local development with ngrok (optional):
# Invoke-RestMethod -Uri "https://your-ngrok-url.ngrok-free.app/webhook" -Method POST -Headers @{"Content-Type"="application/json"} -Body $payload
```

#### Expected Results
- **Before Fix**: First request takes 7+ seconds, second hangs
- **After Fix**: Both requests complete in < 1 second

### Performance Benchmarks

#### Webhook Response Times
- **Target**: < 1 second per request
- **Maximum**: < 2 seconds per request
- **Concurrency**: Unlimited concurrent requests

#### Signal Processing
- **Background Processing**: Continues asynchronously
- **Error Handling**: Non-retryable errors fail immediately
- **Retry Logic**: Only for transient API errors

### Continuous Integration

#### GitHub Actions (if using)
```yaml
- name: Test Webhook Concurrency
  run: |
    python -m pytest tests/test_webhook_concurrency.py -v
    python -m pytest tests/test_webhook_handler_async.py -v
```

#### Local Development
```bash
# Run before committing
python -m pytest tests/test_webhook_*.py

# Full test suite
python -m pytest --cov=src

# Performance testing
python tests/run_webhook_tests.py
```

### Troubleshooting Tests

#### Common Test Failures

**Connection Refused**
- Ensure bot is running: `python run_bot.py`
- Check port configuration in config.yaml
- Verify firewall settings

**Timeout Errors**
- Check bot logs for errors
- Verify Alpaca API credentials
- Test with simpler payloads

**Assertion Failures**
- Review webhook response times in logs
- Check if retry logic is properly configured
- Verify error classification in order manager

#### Debug Mode
```bash
# Run tests with detailed output
python -m pytest tests/test_webhook_concurrency.py -v -s

# Run with webhook URL override
TEST_WEBHOOK_URL=http://localhost:8080/webhook python -m pytest tests/test_webhook_concurrency.py
```

### Test Data Analysis

The test runner provides detailed metrics:
- Response time statistics (min, max, average)
- Success/failure rates
- Concurrent request handling
- Error classification accuracy

## Integration with Main Documentation

This testing documentation complements the main README.md which provides:
- Complete setup and configuration
- Production deployment guidelines
- Architecture overview
- Webhook fix implementation details

All testing procedures are designed to validate the webhook fix implemented to resolve the blocking issue described in the main documentation.
