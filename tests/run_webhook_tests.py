#!/usr/bin/env python3
"""
Webhook test runner with environment detection.
Automatically detects your webhook URL and runs comprehensive tests.
"""

import sys
import os
import subprocess
import requests
from test_config import get_webhook_url, get_test_config


def detect_webhook_url():
    """Try to detect the active webhook URL."""
    urls_to_try = [
        get_webhook_url("local"),
        get_webhook_url("ngrok"),
        "http://localhost:8080/webhook"
    ]
    
    for url in urls_to_try:
        try:
            # Try to reach the health endpoint
            health_url = url.replace("/webhook", "/health")
            response = requests.get(health_url, timeout=5)
            if response.status_code == 200:
                print(f"✅ Found active webhook at: {url}")
                return url
        except:
            continue
    
    return None


def run_webhook_tests(webhook_url=None):
    """Run the webhook test suite."""
    if not webhook_url:
        webhook_url = detect_webhook_url()
        
        if not webhook_url:
            print("❌ No active webhook found. Make sure your bot is running.")
            print("   You can manually specify a URL:")
            print(f"   python {sys.argv[0]} https://your-ngrok-url.ngrok-free.app/webhook")
            return False
    
    print(f"🧪 Running webhook tests against: {webhook_url}")
    print("=" * 60)
    
    # Set environment variable for tests
    os.environ["TEST_WEBHOOK_URL"] = webhook_url
    
    # Run the test suite
    test_commands = [
        ["python", "-m", "pytest", "tests/test_webhook_concurrency.py", "-v"],
        ["python", "-m", "pytest", "tests/test_webhook_handler_async.py", "-v"]
    ]
    
    success = True
    for cmd in test_commands:
        print(f"\n🔧 Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Test passed")
        else:
            print("❌ Test failed")
            print(result.stdout)
            print(result.stderr)
            success = False
    
    # Also run the manual concurrency test
    print(f"\n🚀 Running manual concurrency test...")
    try:
        from test_webhook_concurrency import WebhookConcurrencyTestRunner
        runner = WebhookConcurrencyTestRunner(webhook_url)
        result = runner.run_comprehensive_test(num_requests=3)
        
        if result.get("test_passed", False):
            print("✅ Manual concurrency test passed")
        else:
            print("❌ Manual concurrency test failed")
            success = False
            
    except Exception as e:
        print(f"❌ Error running manual test: {e}")
        success = False
    
    return success


def main():
    """Main test runner."""
    webhook_url = None
    
    if len(sys.argv) > 1:
        webhook_url = sys.argv[1]
    
    print("Webhook Test Runner")
    print("=" * 60)
    print("This script tests webhook concurrency and non-blocking behavior.")
    print()
    
    success = run_webhook_tests(webhook_url)
    
    if success:
        print("\n🎉 All webhook tests passed!")
        print("   Your webhook handler is working correctly.")
    else:
        print("\n💥 Some tests failed!")
        print("   Check the output above for details.")
        print("   Make sure your bot is running and accessible.")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
