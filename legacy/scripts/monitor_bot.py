#!/usr/bin/env python3
"""
Trading Bot Monitor and Controller
Provides a simple interface to monitor and control the trading bot.
"""

import time
import requests
import subprocess
import sys
from pathlib import Path

class BotController:
    def __init__(self):
        self.bot_url = "http://localhost:8080"
        self.bot_process = None
    
    def is_bot_running(self):
        """Check if bot is running by pinging health endpoint."""
        try:
            response = requests.get(f"{self.bot_url}/health", timeout=2)
            return response.status_code == 200
        except Exception:
            return False
    
    def shutdown_bot(self):
        """Send shutdown command to bot."""
        try:
            response = requests.post(f"{self.bot_url}/admin/shutdown", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
    
    def force_kill_bot(self):
        """Force kill bot processes."""
        try:
            # Run the stop_bot.bat script
            subprocess.run(["stop_bot.bat"], shell=True, check=True)
            return True
        except Exception:
            return False
    
    def monitor_bot(self):
        """Monitor bot and provide control options."""
        print("🤖 Trading Bot Monitor")
        print("=" * 30)
        
        while True:
            if self.is_bot_running():
                print(f"✅ Bot is running - {time.strftime('%H:%M:%S')}")
                print("\nOptions:")
                print("1. Continue monitoring")
                print("2. Shutdown bot gracefully")
                print("3. Force kill bot")
                print("4. Exit monitor")
                
                choice = input("\nEnter choice (1-4): ").strip()
                
                if choice == "2":
                    print("🛑 Sending shutdown command...")
                    if self.shutdown_bot():
                        print("✅ Shutdown command sent")
                        print("⏳ Waiting for bot to stop...")
                        for i in range(10):
                            if not self.is_bot_running():
                                print("🏁 Bot stopped successfully")
                                return
                            time.sleep(1)
                        print("⚠️ Bot didn't stop, try force kill")
                    else:
                        print("❌ Shutdown command failed")
                
                elif choice == "3":
                    print("💥 Force killing bot...")
                    if self.force_kill_bot():
                        print("🏁 Bot processes terminated")
                        return
                    else:
                        print("❌ Force kill failed")
                
                elif choice == "4":
                    print("👋 Exiting monitor")
                    return
                
                elif choice == "1":
                    pass  # Continue monitoring
                else:
                    print("❌ Invalid choice")
                
            else:
                print(f"❌ Bot is not running - {time.strftime('%H:%M:%S')}")
                print("\nBot appears to be stopped.")
                choice = input("Check again? (y/n): ").strip().lower()
                if choice != 'y':
                    return
            
            print("\n" + "-" * 30)
            time.sleep(2)

if __name__ == "__main__":
    controller = BotController()
    try:
        controller.monitor_bot()
    except KeyboardInterrupt:
        print("\n👋 Monitor stopped")
