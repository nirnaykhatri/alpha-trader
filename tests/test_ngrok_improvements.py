#!/usr/bin/env python3
"""
Test script for the improved ngrok manager.
"""

import sys
import os
import asyncio

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.ngrok_manager import NgrokManager

async def test_ngrok_improvements():
    """Test the improved ngrok manager."""
    
    print("Testing improved ngrok manager...")
    print("=" * 50)
    
    # Create ngrok manager
    manager = NgrokManager()
    
    # Test health check before starting
    print("🔍 Initial health check:")
    health = manager._check_ngrok_health()
    for key, value in health.items():
        print(f"   {key}: {value}")
    
    print("\n🚀 Attempting to start ngrok tunnel...")
    
    # Try to start tunnel with improved error handling
    try:
        tunnel_url = await manager.start_tunnel(8080)
        
        if tunnel_url:
            print(f"\n✅ SUCCESS! Tunnel URL: {tunnel_url}")
            print("\n🔍 Health check after successful start:")
            health = manager._check_ngrok_health()
            for key, value in health.items():
                print(f"   {key}: {value}")
            
            # Display tunnel info
            manager.display_tunnel_info()
            
            print("\n⏳ Tunnel will run for 10 seconds for testing...")
            await asyncio.sleep(10)
            
            print("\n🛑 Stopping tunnel...")
            manager.stop_tunnel()
            
        else:
            print("\n❌ Failed to start tunnel")
            print("\n🔍 Health check after failure:")
            health = manager._check_ngrok_health()
            for key, value in health.items():
                print(f"   {key}: {value}")
        
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
        manager.stop_tunnel()
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        manager.stop_tunnel()
    
    print("\n✅ Test completed!")

if __name__ == "__main__":
    asyncio.run(test_ngrok_improvements())
