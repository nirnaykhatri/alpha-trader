#!/usr/bin/env python3
"""
Test webhook security configuration
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.configuration import ConfigurationManager

def test_webhook_security():
    """Test webhook security configuration"""
    print("🔧 Testing Webhook Security Configuration")
    print("="*50)
    
    config = ConfigurationManager('config.yaml')
    
    # Get current settings
    security_enabled = config.get_config('api.webhook.security_enabled', True)
    secret = config.get_config('api.webhook.secret', '')
    host = config.get_config('api.webhook.host', '0.0.0.0')
    port = config.get_config('api.webhook.port', 8080)
    
    print(f"Security Enabled: {security_enabled}")
    print(f"Secret: {'Set' if secret else 'Not Set'}")
    print(f"Host: {host}")
    print(f"Port: {port}")
    
    print("\n📡 Webhook Endpoints:")
    if security_enabled:
        print(f"🔒 Secure: http://{host}:{port}/webhook/{{your-secret}}")
        print(f"🔓 Legacy: http://{host}:{port}/webhook (with signature/secret in body)")
    else:
        print(f"🔓 Development: http://{host}:{port}/webhook")
        print(f"🔓 With path: http://{host}:{port}/webhook/any-value-ignored")
    
    print("\n📋 TradingView Webhook URL Examples:")
    if security_enabled:
        print("⚠️  Production mode - secret required:")
        print(f"   https://your-ngrok-url.ngrok.io/webhook/{secret if secret else 'YOUR-SECRET-HERE'}")
    else:
        print("✅ Development mode - no secret required:")
        print("   https://your-ngrok-url.ngrok.io/webhook")
    
    print("\n📝 TradingView Alert Message:")
    template = '''{
  "ticker": "{{ticker}}",
  "time": "{{time}}",
  "interval": "{{interval}}",
  "signal": "{{strategy.order.action}}",
  "price": "{{close}}",
  "message": "Alert for {{ticker}}"
}'''
    print(template)

if __name__ == "__main__":
    test_webhook_security()
