#!/usr/bin/env python3
"""
Standalone ngrok tunnel manager.
Runs ngrok as a completely separate process for improved shutdown behavior.
"""

import os
import sys
import json
import time
import signal
import asyncio
import argparse
import urllib.request
from pathlib import Path
from typing import Optional
import logging

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.utils.ngrok_manager import NgrokManager
from src.core.configuration import ConfigurationManager

logger = logging.getLogger(__name__)


class StandaloneNgrokService:
    """Standalone ngrok service that runs independently of the trading bot."""
    
    def __init__(self, port: int = 8080, config_path: Optional[str] = None):
        self.port = port
        self.config_path = config_path or "config.yaml"
        self.ngrok_manager: Optional[NgrokManager] = None
        self.config_manager: Optional[ConfigurationManager] = None
        self.running = False
        self._shutdown_event = asyncio.Event()
        
    async def initialize(self):
        """Initialize the ngrok service."""
        try:
            # Initialize configuration
            if os.path.exists(self.config_path):
                self.config_manager = ConfigurationManager(self.config_path)
            
            # Initialize ngrok manager
            self.ngrok_manager = NgrokManager(self.config_manager)
            
            # Setup signal handlers for graceful shutdown
            self._setup_signal_handlers()
            
            print("✅ Standalone ngrok service initialized")
            return True
            
        except Exception as e:
            print(f"❌ Failed to initialize ngrok service: {e}")
            logger.error(f"Failed to initialize ngrok service: {e}")
            return False
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            print(f"\n🛑 Received signal {signum}, shutting down ngrok service...")
            self._shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def start_tunnel(self) -> Optional[str]:
        """Start the ngrok tunnel."""
        if not self.ngrok_manager:
            print("❌ Ngrok manager not initialized")
            return None
        
        try:
            print(f"🚇 Starting ngrok tunnel for port {self.port}...")
            tunnel_url = await self.ngrok_manager.start_tunnel(self.port)
            
            if tunnel_url:
                self.running = True
                print("=" * 70)
                print("🎉 STANDALONE NGROK TUNNEL READY!")
                print("=" * 70)
                print(f"🌐 Public URL: {tunnel_url}")
                print(f"🎯 Webhook URL: {tunnel_url}/webhook")
                print(f"📊 Monitor traffic: http://localhost:4040")
                print()
                print("📋 COPY THIS TO TRADINGVIEW:")
                print(f"   {tunnel_url}/webhook")
                print()
                print("⚠️  Note: This tunnel is running independently")
                print("   You can start/stop your trading bot without affecting the tunnel")
                print("   Press Ctrl+C to stop this tunnel service")
                print("=" * 70)
                return tunnel_url
            else:
                print("❌ Failed to start ngrok tunnel")
                return None
                
        except Exception as e:
            print(f"❌ Error starting tunnel: {e}")
            logger.error(f"Error starting tunnel: {e}")
            return None
    
    async def monitor_tunnel(self):
        """Monitor the tunnel and keep it alive."""
        check_interval = 30  # Check every 30 seconds
        consecutive_failures = 0
        max_failures = 3
        
        while self.running and not self._shutdown_event.is_set():
            try:
                # Check if ngrok process is still running
                if self.ngrok_manager and not self.ngrok_manager.is_tunnel_active():
                    consecutive_failures += 1
                    print(f"⚠️  Tunnel check failed ({consecutive_failures}/{max_failures})")
                    
                    if consecutive_failures >= max_failures:
                        print("❌ Tunnel appears to be down after multiple checks")
                        break
                else:
                    if consecutive_failures > 0:
                        print("✅ Tunnel check passed")
                    consecutive_failures = 0
                
                # Wait for next check or shutdown signal
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=check_interval)
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    continue  # Normal timeout, continue monitoring
                    
            except Exception as e:
                logger.error(f"Error monitoring tunnel: {e}")
                consecutive_failures += 1
                if consecutive_failures >= max_failures:
                    break
                await asyncio.sleep(5)
    
    async def stop_tunnel(self):
        """Stop the ngrok tunnel."""
        print("🛑 Stopping ngrok tunnel service...")
        self.running = False
        self._shutdown_event.set()
        
        if self.ngrok_manager:
            self.ngrok_manager.stop_tunnel()
        
        print("✅ Ngrok tunnel service stopped")
    
    async def run(self) -> bool:
        """Run the standalone ngrok service."""
        if not await self.initialize():
            return False
        
        # Start the tunnel
        tunnel_url = await self.start_tunnel()
        if not tunnel_url:
            return False
        
        try:
            # Monitor the tunnel until shutdown
            await self.monitor_tunnel()
        except KeyboardInterrupt:
            print("\n🛑 Received Ctrl+C, shutting down...")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            logger.error(f"Unexpected error in ngrok service: {e}")
        finally:
            await self.stop_tunnel()
        
        return True


async def main():
    """Main entry point for standalone ngrok service."""
    parser = argparse.ArgumentParser(description="Standalone ngrok tunnel service")
    parser.add_argument("--port", type=int, default=8080, help="Port to tunnel (default: 8080)")
    parser.add_argument("--config", type=str, help="Path to config.yaml file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    else:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    print("=" * 70)
    print("🚇 STANDALONE NGROK TUNNEL SERVICE")
    print("=" * 70)
    print(f"Port: {args.port}")
    print(f"Config: {args.config or 'config.yaml'}")
    print()
    
    # Create and run the service
    service = StandaloneNgrokService(port=args.port, config_path=args.config)
    
    try:
        success = await service.run()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        logger.error(f"Fatal error in standalone ngrok service: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Ensure we're using the right event loop policy on Windows
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(main())
