#!/usr/bin/env python3
"""
Utility to check if ngrok is running externally and get tunnel information.
"""

import json
import urllib.request
from typing import Optional, Dict, Any


def check_external_ngrok() -> Dict[str, Any]:
    """
    Check if ngrok is running externally and return tunnel information.
    
    Returns:
        Dict with keys:
        - 'running': bool - whether ngrok is accessible
        - 'tunnel_url': str or None - the public tunnel URL
        - 'webhook_url': str or None - the webhook URL
        - 'monitor_url': str - the ngrok monitor URL
        - 'tunnels': list - all available tunnels
        - 'error': str or None - error message if any
    """
    result = {
        'running': False,
        'tunnel_url': None,
        'webhook_url': None,
        'monitor_url': 'http://localhost:4040',
        'tunnels': [],
        'error': None
    }
    
    try:
        # Try to connect to ngrok API
        api_endpoints = [
            "http://localhost:4040/api/tunnels",
            "http://127.0.0.1:4040/api/tunnels"
        ]
        
        data = None
        for api_url in api_endpoints:
            try:
                with urllib.request.urlopen(api_url, timeout=5) as response:
                    data = json.loads(response.read().decode())
                    break
            except Exception:
                continue
        
        if not data:
            result['error'] = "Cannot connect to ngrok API (not running or port 4040 blocked)"
            return result
        
        result['running'] = True
        result['tunnels'] = data.get("tunnels", [])
        
        # Find the best tunnel (prefer HTTPS)
        best_tunnel = None
        for tunnel in result['tunnels']:
            if tunnel.get("proto") == "https":
                best_tunnel = tunnel
                break
        
        # Fallback to HTTP tunnel
        if not best_tunnel:
            for tunnel in result['tunnels']:
                if tunnel.get("proto") == "http":
                    best_tunnel = tunnel
                    break
        
        if best_tunnel:
            tunnel_url = best_tunnel.get("public_url")
            if tunnel_url:
                # Ensure HTTPS for TradingView compatibility
                if tunnel_url.startswith("http://"):
                    tunnel_url = tunnel_url.replace("http://", "https://")
                
                result['tunnel_url'] = tunnel_url
                result['webhook_url'] = f"{tunnel_url}/webhook"
        
        return result
        
    except Exception as e:
        result['error'] = f"Error checking ngrok: {str(e)}"
        return result


def display_ngrok_status():
    """Display the current ngrok status in a user-friendly format."""
    status = check_external_ngrok()
    
    print("=" * 60)
    print("🔍 NGROK STATUS CHECK")
    print("=" * 60)
    
    if status['running']:
        print("✅ Ngrok is running!")
        print(f"📊 Monitor: {status['monitor_url']}")
        
        if status['tunnel_url']:
            print(f"🌐 Public URL: {status['tunnel_url']}")
            print(f"🎯 Webhook URL: {status['webhook_url']}")
            print()
            print("📋 For TradingView webhook settings:")
            print(f"   {status['webhook_url']}")
        else:
            print("⚠️  No suitable tunnel found")
        
        if status['tunnels']:
            print()
            print("🚇 Available tunnels:")
            for i, tunnel in enumerate(status['tunnels'], 1):
                proto = tunnel.get('proto', 'unknown')
                url = tunnel.get('public_url', 'unknown')
                local = tunnel.get('config', {}).get('addr', 'unknown')
                print(f"   {i}. {proto.upper()}: {url} -> {local}")
    else:
        print("❌ Ngrok is not running")
        if status['error']:
            print(f"   Error: {status['error']}")
        print()
        print("💡 To start ngrok separately:")
        print("   1. Run: start_ngrok_standalone.bat")
        print("   2. Or manually: ngrok http 8080")
    
    print("=" * 60)
    return status


if __name__ == "__main__":
    display_ngrok_status()
