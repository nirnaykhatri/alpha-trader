#!/usr/bin/env python3
"""
Trading Bot Shutdown Tool
Gracefully shuts down the trading bot when Ctrl+C doesn't work.
"""

import requests
import sys
import time

def shutdown_bot():
    """Send shutdown request to the bot."""
    print("🛑 Trading Bot Shutdown Tool")
    print("="*40)
    
    try:
        print("📡 Connecting to bot at http://localhost:8080...")
        response = requests.post("http://localhost:8080/admin/shutdown", 
                               json={"action": "shutdown"},
                               timeout=10)
        
        if response.status_code == 200:
            print("✅ Shutdown command sent successfully!")
            print("⏳ Bot is shutting down gracefully...")
            
            # Wait a moment and check if bot is still running
            time.sleep(3)
            try:
                health_check = requests.get("http://localhost:8080/health", timeout=2)
                if health_check.status_code == 200:
                    print("⚠️ Bot is still running after 3 seconds")
                    print("💡 If it doesn't shut down soon, try: stop_bot.bat")
                else:
                    print("🏁 Bot has stopped successfully!")
            except requests.exceptions.ConnectionError:
                print("🏁 Bot has stopped successfully!")
                
        elif response.status_code == 403:
            print("❌ Shutdown denied - security restriction")
            print("💡 The bot only accepts shutdown commands from localhost")
        else:
            print(f"❌ Shutdown failed with status: {response.status_code}")
            print("💡 Try using: stop_bot.bat for force shutdown")
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to bot")
        print("💡 Bot might not be running, or check if it's on port 8080")
        print("💡 If it's stuck, use: stop_bot.bat")
    except requests.exceptions.Timeout:
        print("❌ Shutdown request timed out")
        print("💡 Bot might be unresponsive, try: stop_bot.bat")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        print("💡 Try using: stop_bot.bat for force shutdown")

def main():
    """Main function."""
    try:
        shutdown_bot()
    except KeyboardInterrupt:
        print("\n👋 Shutdown cancelled by user")
    
    print("\n📋 Available shutdown methods:")
    print("   • python shutdown_bot.py    (this script)")
    print("   • stop_bot.bat             (force kill)")
    print("   • python monitor_bot.py     (interactive)")
    print("   • Ctrl+Break               (in bot terminal)")

if __name__ == "__main__":
    main()
