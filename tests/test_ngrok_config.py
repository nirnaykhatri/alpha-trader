#!/usr/bin/env python3
"""
Test the ngrok integration with auth token from config.yaml
"""

import sys
import os
import asyncio

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.core.configuration import ConfigurationManager
from src.utils.ngrok_manager import NgrokManager

async def test_ngrok_with_config():
    """Test ngrok integration with the configuration manager."""
    
    print("🧪 Testing ngrok integration with config.yaml auth token...")
    print("=" * 60)
    
    try:
        # Initialize config manager (should load config.yaml)
        config_manager = ConfigurationManager()
        
        # Check if ngrok is enabled
        ngrok_enabled = config_manager.get_config("ngrok.enabled", False)
        print(f"📋 ngrok.enabled: {ngrok_enabled}")
        
        # Check auth token (don't print full token for security)
        auth_token = config_manager.get_config("ngrok.auth_token")
        if auth_token:
            print(f"🔐 Auth token configured: {'*' * 20}{auth_token[-8:] if len(auth_token) > 8 else '***'}")
        else:
            print("❌ No auth token found in config")
        
        if not ngrok_enabled:
            print("⚠️  ngrok is disabled in config.yaml")
            return
        
        # Test ngrok manager
        ngrok_manager = NgrokManager(config_manager)
        
        # Test auth token retrieval
        token_test = ngrok_manager._get_auth_token()
        if token_test:
            print("✅ NgrokManager can retrieve auth token")
        else:
            print("❌ NgrokManager cannot retrieve auth token")
            return
        
        print("\n🚇 Testing ngrok tunnel startup...")
        
        # Test tunnel creation
        tunnel_url = await ngrok_manager.start_tunnel(8080)
        
        if tunnel_url:
            print(f"\n🎉 SUCCESS! Tunnel created: {tunnel_url}")
            print("✅ ngrok integration is working properly!")
            
            # Test tunnel info
            ngrok_manager.display_tunnel_info()
            
            print("\n⏳ Keeping tunnel alive for 15 seconds...")
            await asyncio.sleep(15)
            
            print("\n🛑 Stopping tunnel...")
            ngrok_manager.stop_tunnel()
            print("✅ Tunnel stopped successfully")
            
        else:
            print("❌ Failed to create tunnel")
            # Display health check for debugging
            health = ngrok_manager._check_ngrok_health()
            print("\n🔍 Health check results:")
            for key, value in health.items():
                print(f"   {key}: {value}")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ Test completed!")

if __name__ == "__main__":
    asyncio.run(test_ngrok_with_config())
