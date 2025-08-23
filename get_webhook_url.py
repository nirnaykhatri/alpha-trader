#!/usr/bin/env python3
"""
Quick Webhook URL Display
Shows the current ngrok webhook URL if the bot is running with ngrok enabled.
"""

import sys
import json
import urllib.request
from pathlib import Path

def get_webhook_url():
    """Get the current webhook URL from ngrok."""
    try:
        # Check if ngrok is running
        api_url = "http://localhost:4040/api/tunnels"
        
        with urllib.request.urlopen(api_url, timeout=5) as response:
            data = json.loads(response.read().decode())
            
        tunnels = data.get("tunnels", [])
        for tunnel in tunnels:
            if tunnel.get("proto") == "https":
                public_url = tunnel.get("public_url")
                if public_url:
                    return f"{public_url}/webhook"
        
        return None
        
    except Exception as e:
        return None

def main():
    """Main function to display webhook URL."""
    print("🔍 Checking for active ngrok tunnel...")
    
    webhook_url = get_webhook_url()
    
    if webhook_url:
        print("\n✅ Found active ngrok tunnel!")
        print("=" * 60)
        print("🎯 WEBHOOK URL FOR TRADINGVIEW:")
        print(f"   {webhook_url}")
        print("=" * 60)
        print("📊 Monitor webhook traffic at: http://localhost:4040")
        print("\n📋 Copy the webhook URL above to your TradingView alert settings")
    else:
        print("\n❌ No active ngrok tunnel found")
        print("\n💡 To start ngrok automatically:")
        print("   1. Set 'ngrok.enabled: true' in config.yaml")
        print("   2. Run: python run_bot.py")
        print("\n💡 Or start ngrok manually:")
        print("   1. Run: ngrok http 8080")
        print("   2. Copy the HTTPS URL to TradingView")

if __name__ == "__main__":
    main()
