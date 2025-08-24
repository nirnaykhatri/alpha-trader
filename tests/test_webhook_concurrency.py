#!/usr/bin/env python3
"""
Test suite to verify webhook handling fix.
Tests that multiple webhook requests don't get stuck and respond immediately.
"""

import pytest
import requests
import time
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any


class TestWebhookConcurrency:
    """Test cases for webhook concurrency and non-blocking behavior."""
    
    @pytest.fixture
    def webhook_url(self):
        """Webhook URL - should be configured for your test environment."""
        # This should be set via environment variable or test configuration
        return "http://localhost:8080/webhook"
    
    @pytest.fixture
    def test_payload(self):
        """Standard test payload that will trigger order processing."""
        return {
            "symbol": "RGTI",
            "action": "sell",  # This will trigger short sell and fail quickly
            "price": 13.48,
            "quantity": 148
        }
    
    def send_webhook_request(self, url: str, payload: dict, request_id: int) -> Dict[str, Any]:
        """Send a single webhook request and measure response time."""
        try:
            start_time = time.time()
            
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10  # 10 second timeout
            )
            
            response_time = time.time() - start_time
            
            return {
                "request_id": request_id,
                "status_code": response.status_code,
                "response_time": response_time,
                "response_data": response.json() if response.status_code == 200 else None,
                "success": response.status_code == 200
            }
            
        except Exception as e:
            return {
                "request_id": request_id,
                "error": str(e),
                "success": False
            }
    
    def test_webhook_single_request(self, webhook_url, test_payload):
        """Test that a single webhook request responds quickly."""
        result = self.send_webhook_request(webhook_url, test_payload, 1)
        
        assert result["success"], f"Webhook request failed: {result.get('error')}"
        assert result["response_time"] < 2.0, f"Webhook response too slow: {result['response_time']:.3f}s"
        assert "signal_id" in result["response_data"], "Response missing signal_id"
    
    def test_webhook_concurrent_requests(self, webhook_url, test_payload):
        """Test that multiple concurrent webhook requests all respond quickly."""
        num_requests = 3
        results = []
        
        with ThreadPoolExecutor(max_workers=num_requests) as executor:
            # Submit all requests
            futures = [
                executor.submit(self.send_webhook_request, webhook_url, test_payload, i+1)
                for i in range(num_requests)
            ]
            
            # Collect results as they complete
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
        
        # All requests should succeed
        successful_requests = [r for r in results if r["success"]]
        assert len(successful_requests) == num_requests, f"Only {len(successful_requests)}/{num_requests} requests succeeded"
        
        # All requests should be fast
        response_times = [r["response_time"] for r in successful_requests]
        max_response_time = max(response_times)
        assert max_response_time < 2.0, f"Some responses were too slow. Max: {max_response_time:.3f}s"
        
        # All requests should return valid signal IDs
        for result in successful_requests:
            assert "signal_id" in result["response_data"], f"Request {result['request_id']} missing signal_id"
    
    def test_webhook_rapid_succession(self, webhook_url, test_payload):
        """Test that rapid successive requests don't interfere with each other."""
        results = []
        
        # Send requests in rapid succession (not concurrent)
        for i in range(3):
            result = self.send_webhook_request(webhook_url, test_payload, i+1)
            results.append(result)
            # Small delay between requests
            time.sleep(0.1)
        
        # All should succeed and be fast
        for result in results:
            assert result["success"], f"Request {result['request_id']} failed: {result.get('error')}"
            assert result["response_time"] < 2.0, f"Request {result['request_id']} too slow: {result['response_time']:.3f}s"
    
    def test_webhook_different_payloads(self, webhook_url):
        """Test webhook with different payload types."""
        payloads = [
            {"symbol": "AAPL", "action": "buy", "price": 150.0, "quantity": 100},
            {"symbol": "TSLA", "action": "sell", "price": 250.0, "quantity": 50},
            {"symbol": "MSFT", "action": "close", "price": 300.0, "quantity": 75},
        ]
        
        results = []
        for i, payload in enumerate(payloads):
            result = self.send_webhook_request(webhook_url, payload, i+1)
            results.append(result)
        
        # All should succeed and be fast
        for result in results:
            assert result["success"], f"Request {result['request_id']} failed: {result.get('error')}"
            assert result["response_time"] < 2.0, f"Request {result['request_id']} too slow: {result['response_time']:.3f}s"


class WebhookConcurrencyTestRunner:
    """Standalone test runner for manual testing."""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    def run_comprehensive_test(self, num_requests: int = 3) -> Dict[str, Any]:
        """Run comprehensive webhook concurrency test."""
        print("Webhook Concurrency Test")
        print("=" * 50)
        print(f"URL: {self.webhook_url}")
        print(f"Requests: {num_requests}")
        print()
        
        # Test payload that will trigger short sell (which should fail quickly)
        payload = {
            "symbol": "RGTI",
            "action": "sell",  # This will trigger short sell and fail
            "price": 13.48,
            "quantity": 148
        }
        
        print(f"Test payload: {json.dumps(payload, indent=2)}")
        print("-" * 50)
        
        # Send requests concurrently
        results = []
        test_instance = TestWebhookConcurrency()
        
        with ThreadPoolExecutor(max_workers=num_requests) as executor:
            # Submit all requests
            futures = [
                executor.submit(test_instance.send_webhook_request, self.webhook_url, payload, i+1)
                for i in range(num_requests)
            ]
            
            # Collect results as they complete
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                
                if result["success"]:
                    print(f"✅ Request {result['request_id']}: "
                          f"{result['response_time']:.3f}s - {result['response_data']}")
                else:
                    error_msg = result.get('error', f"HTTP {result.get('status_code', 'Unknown')}")
                    print(f"❌ Request {result['request_id']}: Error - {error_msg}")
        
        # Analyze results
        print("-" * 50)
        successful_requests = [r for r in results if r["success"]]
        
        analysis = {
            "total_requests": num_requests,
            "successful_requests": len(successful_requests),
            "failed_requests": num_requests - len(successful_requests),
            "results": results
        }
        
        if len(successful_requests) >= 2:
            response_times = [r["response_time"] for r in successful_requests]
            analysis.update({
                "avg_response_time": sum(response_times) / len(response_times),
                "max_response_time": max(response_times),
                "min_response_time": min(response_times)
            })
            
            print(f"📊 Results:")
            print(f"   - Successful requests: {len(successful_requests)}/{num_requests}")
            print(f"   - Average response time: {analysis['avg_response_time']:.3f}s")
            print(f"   - Max response time: {analysis['max_response_time']:.3f}s")
            print(f"   - Min response time: {analysis['min_response_time']:.3f}s")
            
            if analysis['max_response_time'] < 2.0:
                print(f"✅ SUCCESS: All responses were fast (< 2s)")
                print(f"   The webhook handler is working correctly!")
                analysis["test_passed"] = True
            else:
                print(f"⚠️  WARNING: Some responses were slow (> 2s)")
                print(f"   There might still be blocking issues.")
                analysis["test_passed"] = False
        else:
            print(f"❌ FAILURE: Only {len(successful_requests)} requests succeeded")
            print(f"   Check if the bot is running and accessible.")
            analysis["test_passed"] = False
        
        return analysis


def run_manual_test(webhook_url: str = None):
    """Run manual webhook concurrency test."""
    if not webhook_url:
        webhook_url = input("Enter webhook URL (e.g., https://your-ngrok-url.ngrok-free.app/webhook): ")
    
    runner = WebhookConcurrencyTestRunner(webhook_url)
    result = runner.run_comprehensive_test(num_requests=3)
    
    print()
    print("Note: Check your bot logs to see the order processing failures.")
    print("The key is that webhook responses should be immediate!")
    
    return result


if __name__ == "__main__":
    # For manual testing
    import sys
    
    webhook_url = None
    if len(sys.argv) > 1:
        webhook_url = sys.argv[1]
    
    run_manual_test(webhook_url)
