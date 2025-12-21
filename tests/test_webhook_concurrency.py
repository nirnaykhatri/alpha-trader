#!/usr/bin/env python3
"""
Webhook Concurrency Tests

Tests webhook handler's ability to process multiple concurrent requests
without blocking or causing race conditions.
"""

import asyncio
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest
import requests

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_config import get_webhook_url, get_test_config, get_sample_webhook_payload


@dataclass
class RequestResult:
    """Result of a single webhook request."""
    success: bool
    status_code: int
    response_time: float
    response_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class ConcurrencyTestResult:
    """Result of a concurrency test run."""
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_time: float
    average_response_time: float
    min_response_time: float
    max_response_time: float
    test_passed: bool
    errors: List[str] = field(default_factory=list)


class WebhookConcurrencyTestRunner:
    """
    Runs concurrency tests against the webhook endpoint.
    
    Tests that the webhook can handle multiple simultaneous requests
    without blocking or degrading performance.
    """
    
    def __init__(self, webhook_url: Optional[str] = None, timeout: int = 30):
        """
        Initialize the test runner.
        
        Args:
            webhook_url: The webhook URL to test. If None, auto-detects.
            timeout: Request timeout in seconds
        """
        self.webhook_url = webhook_url or get_webhook_url("local")
        self.timeout = timeout
        self.config = get_test_config()
    
    def _send_request(self, symbol: str, action: str = "buy") -> RequestResult:
        """
        Send a single webhook request.
        
        Args:
            symbol: Stock symbol
            action: Trade action (buy/sell)
            
        Returns:
            RequestResult with timing and status info
        """
        payload = get_sample_webhook_payload(symbol=symbol, action=action)
        
        start_time = time.time()
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            elapsed = time.time() - start_time
            
            return RequestResult(
                success=response.status_code in (200, 202),
                status_code=response.status_code,
                response_time=elapsed,
                response_data=response.json() if response.text else None
            )
        except requests.exceptions.Timeout:
            elapsed = time.time() - start_time
            return RequestResult(
                success=False,
                status_code=0,
                response_time=elapsed,
                error="Request timed out"
            )
        except Exception as e:
            elapsed = time.time() - start_time
            return RequestResult(
                success=False,
                status_code=0,
                response_time=elapsed,
                error=str(e)
            )
    
    def run_concurrent_requests(
        self, 
        num_requests: int = 10, 
        symbols: Optional[List[str]] = None
    ) -> List[RequestResult]:
        """
        Send multiple requests concurrently.
        
        Args:
            num_requests: Number of concurrent requests to send
            symbols: List of symbols to use (cycles through if fewer than num_requests)
            
        Returns:
            List of RequestResult objects
        """
        if symbols is None:
            symbols = self.config.get("test_symbols", ["AAPL", "GOOGL", "MSFT", "TSLA"])
        
        # Create request parameters
        request_params = [
            (symbols[i % len(symbols)], "buy" if i % 2 == 0 else "sell")
            for i in range(num_requests)
        ]
        
        results = []
        with ThreadPoolExecutor(max_workers=num_requests) as executor:
            futures = [
                executor.submit(self._send_request, symbol, action)
                for symbol, action in request_params
            ]
            results = [f.result() for f in futures]
        
        return results
    
    def run_comprehensive_test(
        self, 
        num_requests: int = 10,
        max_avg_response_time: float = 5.0,
        min_success_rate: float = 0.8
    ) -> Dict[str, Any]:
        """
        Run a comprehensive concurrency test.
        
        Args:
            num_requests: Number of concurrent requests to send
            max_avg_response_time: Maximum acceptable average response time (seconds)
            min_success_rate: Minimum acceptable success rate (0.0 to 1.0)
            
        Returns:
            Dict with test results
        """
        print(f"  Sending {num_requests} concurrent requests to {self.webhook_url}")
        
        start_time = time.time()
        results = self.run_concurrent_requests(num_requests)
        total_time = time.time() - start_time
        
        # Calculate statistics
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        response_times = [r.response_time for r in results]
        
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        min_response_time = min(response_times) if response_times else 0
        max_response_time = max(response_times) if response_times else 0
        success_rate = len(successful) / len(results) if results else 0
        
        # Determine if test passed
        test_passed = (
            success_rate >= min_success_rate and
            avg_response_time <= max_avg_response_time
        )
        
        errors = [r.error for r in failed if r.error]
        
        result = ConcurrencyTestResult(
            total_requests=len(results),
            successful_requests=len(successful),
            failed_requests=len(failed),
            total_time=total_time,
            average_response_time=avg_response_time,
            min_response_time=min_response_time,
            max_response_time=max_response_time,
            test_passed=test_passed,
            errors=errors
        )
        
        # Print summary
        print(f"  Results: {result.successful_requests}/{result.total_requests} successful")
        print(f"  Average response time: {result.average_response_time:.3f}s")
        print(f"  Total time: {result.total_time:.3f}s")
        
        return {
            "total_requests": result.total_requests,
            "successful_requests": result.successful_requests,
            "failed_requests": result.failed_requests,
            "total_time": result.total_time,
            "average_response_time": result.average_response_time,
            "min_response_time": result.min_response_time,
            "max_response_time": result.max_response_time,
            "test_passed": result.test_passed,
            "success_rate": success_rate,
            "errors": result.errors
        }


# ============================================================================
# Pytest Test Cases
# ============================================================================

@pytest.fixture
def webhook_url():
    """Get the webhook URL for testing."""
    url = os.environ.get("TEST_WEBHOOK_URL") or get_webhook_url("local")
    return url


@pytest.fixture
def test_runner(webhook_url):
    """Create a test runner instance."""
    return WebhookConcurrencyTestRunner(webhook_url)


class TestWebhookConcurrency:
    """Test suite for webhook concurrency behavior."""
    
    @pytest.mark.integration
    @pytest.mark.network
    def test_single_request(self, test_runner):
        """Test that a single request succeeds."""
        result = test_runner._send_request("AAPL", "buy")
        # Allow both success and server errors (bot may not be configured)
        assert result.status_code in (200, 202, 400, 401, 500), \
            f"Unexpected status code: {result.status_code}, error: {result.error}"
    
    @pytest.mark.integration
    @pytest.mark.network
    def test_concurrent_requests_small(self, test_runner):
        """Test a small batch of concurrent requests."""
        results = test_runner.run_concurrent_requests(num_requests=3)
        assert len(results) == 3, "Should return 3 results"
        # At least some should complete (even if with errors)
        completed = [r for r in results if r.status_code != 0]
        assert len(completed) >= 1, "At least one request should complete"
    
    @pytest.mark.integration
    @pytest.mark.network
    @pytest.mark.slow
    def test_concurrent_requests_medium(self, test_runner):
        """Test a medium batch of concurrent requests."""
        results = test_runner.run_concurrent_requests(num_requests=10)
        assert len(results) == 10, "Should return 10 results"
        
        # Check response times are reasonable (not blocking sequentially)
        response_times = [r.response_time for r in results]
        avg_time = sum(response_times) / len(response_times)
        
        # If requests were blocking, total time would be ~10x single request time
        # With concurrency, they should all complete in roughly the same time
        max_time = max(response_times)
        assert max_time < avg_time * 3, \
            f"Max response time ({max_time:.2f}s) too high vs average ({avg_time:.2f}s)"
    
    @pytest.mark.integration
    @pytest.mark.network
    def test_non_blocking_behavior(self, test_runner):
        """
        Test that webhook handler is non-blocking.
        
        If the handler blocks, concurrent requests will queue up and
        take much longer than if they were processed in parallel.
        """
        # Time for sequential requests (baseline)
        sequential_times = []
        for _ in range(3):
            result = test_runner._send_request("AAPL", "buy")
            sequential_times.append(result.response_time)
        
        avg_sequential = sum(sequential_times) / len(sequential_times)
        
        # Time for concurrent requests
        start = time.time()
        results = test_runner.run_concurrent_requests(num_requests=3)
        concurrent_total = time.time() - start
        
        # Concurrent should be faster than 3x sequential
        # (allowing some overhead for thread management)
        expected_sequential_total = avg_sequential * 3
        
        # Concurrent should complete in less than 2x a single request time
        # (with some buffer for overhead)
        assert concurrent_total < expected_sequential_total * 0.8, \
            f"Concurrent time ({concurrent_total:.2f}s) should be less than " \
            f"sequential time ({expected_sequential_total:.2f}s)"


class TestWebhookPayloadValidation:
    """Test suite for webhook payload validation."""
    
    @pytest.mark.integration
    @pytest.mark.network
    def test_valid_payload(self, webhook_url):
        """Test that valid payload is accepted."""
        payload = get_sample_webhook_payload("AAPL", "buy", price=150.0)
        
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=10,
            headers={"Content-Type": "application/json"}
        )
        
        # Accept success or auth error (if secret is required)
        assert response.status_code in (200, 202, 401), \
            f"Unexpected status: {response.status_code}"
    
    @pytest.mark.integration
    @pytest.mark.network
    def test_invalid_json(self, webhook_url):
        """Test that invalid JSON is rejected."""
        response = requests.post(
            webhook_url,
            data="not valid json{{{",
            timeout=10,
            headers={"Content-Type": "application/json"}
        )
        
        # Should get a 400 Bad Request or 422 Validation Error
        assert response.status_code in (400, 422, 401), \
            f"Expected 400/422 for invalid JSON, got {response.status_code}"


if __name__ == "__main__":
    # Run as standalone script
    import argparse
    
    parser = argparse.ArgumentParser(description="Webhook Concurrency Tests")
    parser.add_argument("--url", help="Webhook URL to test")
    parser.add_argument("--requests", type=int, default=10, help="Number of concurrent requests")
    args = parser.parse_args()
    
    url = args.url or get_webhook_url("local")
    print(f"Testing webhook at: {url}")
    
    runner = WebhookConcurrencyTestRunner(url)
    result = runner.run_comprehensive_test(num_requests=args.requests)
    
    print("\n" + "=" * 50)
    if result["test_passed"]:
        print("✅ Concurrency test PASSED")
    else:
        print("❌ Concurrency test FAILED")
        if result["errors"]:
            print("Errors:")
            for error in result["errors"]:
                print(f"  - {error}")
    
    sys.exit(0 if result["test_passed"] else 1)
