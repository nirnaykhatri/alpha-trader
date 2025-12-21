"""
Automated ngrok integration for local webhook development.
Downloads, configures, and manages ngrok tunnel automatically.
"""

import os
import sys
import json
import time
import asyncio
import zipfile
import platform
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional, Dict, Any
import logging

from src.constants import NgrokConstants

logger = logging.getLogger(__name__)


class NgrokManager:
    """Manages ngrok tunnel for local webhook development."""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.ngrok_dir = Path.cwd() / ".ngrok"
        self.ngrok_exe = self._get_ngrok_executable_path()
        self.ngrok_process: Optional[subprocess.Popen] = None
        self.tunnel_url: Optional[str] = None
        self.api_url = f"http://{NgrokConstants.API_HOST}:{NgrokConstants.API_PORT}{NgrokConstants.API_TUNNELS_ENDPOINT}"
        
    def _get_ngrok_executable_path(self) -> Path:
        """Get the path to ngrok executable based on OS."""
        if platform.system() == "Windows":
            return self.ngrok_dir / "ngrok.exe"
        else:
            return self.ngrok_dir / "ngrok"
    
    def _get_download_url(self) -> str:
        """Get the appropriate ngrok download URL for the current OS."""
        system = platform.system().lower()
        machine = platform.machine().lower()
        
        # Map platform to ngrok naming
        if system == "windows":
            if "64" in machine or "amd64" in machine:
                return "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"
            else:
                return "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-386.zip"
        elif system == "darwin":  # macOS
            if "arm64" in machine:
                return "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-arm64.zip"
            else:
                return "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-amd64.zip"
        elif system == "linux":
            if "aarch64" in machine or "arm64" in machine:
                return "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm64.zip"
            elif "arm" in machine:
                return "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm.zip"
            elif "64" in machine:
                return "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.zip"
            else:
                return "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-386.zip"
        else:
            raise RuntimeError(f"Unsupported platform: {system}")
    
    def _download_progress_hook(self, block_num: int, block_size: int, total_size: int):
        """Show download progress."""
        downloaded = block_num * block_size
        if total_size > 0:
            percent = min(100, (downloaded * 100) // total_size)
            print(f"\r📥 Downloading ngrok: {percent}% ({downloaded // 1024}KB / {total_size // 1024}KB)", end="", flush=True)
    
    async def ensure_ngrok_available(self) -> bool:
        """Download and install ngrok if not already available."""
        if self.ngrok_exe.exists():
            logger.info("ngrok already available")
            return True
        
        try:
            print("🔧 ngrok not found, downloading automatically...")
            
            # Create ngrok directory
            self.ngrok_dir.mkdir(exist_ok=True)
            
            # Download ngrok
            download_url = self._get_download_url()
            zip_path = self.ngrok_dir / "ngrok.zip"
            
            print(f"📥 Downloading from: {download_url}")
            urllib.request.urlretrieve(download_url, zip_path, self._download_progress_hook)
            print()  # New line after progress
            
            # Extract ngrok
            print("📦 Extracting ngrok...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.ngrok_dir)
            
            # Make executable on Unix systems
            if platform.system() != "Windows":
                os.chmod(self.ngrok_exe, 0o755)
            
            # Clean up zip file
            zip_path.unlink()
            
            # Verify installation
            if self.ngrok_exe.exists():
                print("✅ ngrok downloaded and installed successfully")
                return True
            else:
                print("❌ Failed to install ngrok")
                return False
                
        except Exception as e:
            logger.error(f"Failed to download ngrok: {e}")
            print(f"❌ Failed to download ngrok: {e}")
            return False
    
    def _get_auth_token(self) -> Optional[str]:
        """Get ngrok auth token from config or environment."""
        # Try config first
        if self.config_manager:
            try:
                token = self.config_manager.get_config("ngrok.auth_token")
                if token and token.strip():
                    return token.strip()
            except Exception as e:
                logger.debug(f"Could not get auth token from config: {e}")
        
        # Try environment variable
        token = os.environ.get("NGROK_AUTH_TOKEN")
        if token and token.strip():
            return token.strip()
        
        return None
    
    def _configure_auth_token(self) -> bool:
        """Configure ngrok auth token if available."""
        token = self._get_auth_token()
        if not token:
            print("⚠️  No ngrok auth token configured")
            print("   You can set NGROK_AUTH_TOKEN environment variable")
            print("   or add 'ngrok.auth_token' to your config.yaml")
            print("   Get a free token from: https://ngrok.com/")
            print("   Note: Free tier has limitations but works for testing")
            print("   ℹ️  Bot will continue with ngrok free tier limitations")
            return False
        
        try:
            # Configure auth token
            print("🔐 Configuring ngrok auth token...")
            result = subprocess.run([
                str(self.ngrok_exe), "config", "add-authtoken", token
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print("✅ ngrok auth token configured successfully")
                return True
            else:
                print(f"⚠️  Failed to configure auth token: {result.stderr}")
                print("   Continuing with free tier limitations...")
                return False
                
        except Exception as e:
            print(f"⚠️  Error configuring auth token: {e}")
            print("   Continuing with free tier limitations...")
            return False
    
    async def start_tunnel(self, port: int) -> Optional[str]:
        """Start ngrok tunnel and return the public URL."""
        if not await self.ensure_ngrok_available():
            return None

        # Configure auth token if available
        auth_configured = self._configure_auth_token()

        try:
            print(f"🚇 Starting ngrok tunnel for port {port}...")
            
            # Start ngrok process with more verbose logging
            cmd = [str(self.ngrok_exe), "http", str(port), "--log=stdout", "--log-level=info"]
            
            # Add region for better performance if auth token is configured
            if auth_configured:
                cmd.extend(["--region", "us"])
            
            print(f"🔧 Running command: {' '.join(cmd)}")
            
            self.ngrok_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Give ngrok a moment to start its web interface
            await asyncio.sleep(NgrokConstants.INITIAL_STARTUP_DELAY)
            
            # Wait for tunnel to be ready with better diagnostics
            max_attempts = NgrokConstants.MAX_STARTUP_ATTEMPTS  # 60 seconds for slower systems
            for attempt in range(max_attempts):
                try:
                    # Check if process is still running
                    if self.ngrok_process.poll() is not None:
                        stdout, stderr = self.ngrok_process.communicate()
                        print(f"🔍 ngrok stdout: {stdout}")
                        print(f"🔍 ngrok stderr: {stderr}")
                        raise RuntimeError(f"ngrok process failed. stderr: {stderr}, stdout: {stdout}")
                    
                    # Show progress every 10 attempts
                    if attempt % 10 == 0 and attempt > 0:
                        print(f"⏳ Still waiting for ngrok tunnel... ({attempt}/{max_attempts} seconds)")
                    
                    # Try to get tunnel info
                    tunnel_url = await self._get_tunnel_url_with_retry()
                    if tunnel_url:
                        self.tunnel_url = tunnel_url
                        print("=" * 60)
                        print("🎉 NGROK TUNNEL READY!")
                        print("=" * 60)
                        print(f"🌐 Public URL: {tunnel_url}")
                        print(f"🎯 Webhook URL: {tunnel_url}/webhook")
                        print(f"📊 Monitor traffic: http://{NgrokConstants.API_HOST}:{NgrokConstants.API_PORT}")
                        print()
                        print("📋 COPY THIS TO TRADINGVIEW:")
                        print(f"   {tunnel_url}/webhook")
                        print()
                        print("⚠️  Note: Free ngrok URLs change on restart")
                        print("   Update TradingView webhook if you restart the bot")
                        print("=" * 60)
                        return tunnel_url
                    
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    if attempt % 10 == 0 and attempt > 0:
                        print(f"🔍 Debug: Attempt {attempt} failed with: {str(e)}")
                    await asyncio.sleep(1)
            
            # Final diagnostic before giving up
            if self.ngrok_process and self.ngrok_process.poll() is None:
                print("🔍 ngrok process is still running but tunnel API not responding")
                print("🔍 This might indicate firewall or network issues")
                # Try to get process output for debugging
                try:
                    stdout, stderr = self.ngrok_process.communicate(timeout=5)
                    print(f"🔍 Final stdout: {stdout}")
                    print(f"🔍 Final stderr: {stderr}")
                except Exception as e:
                    logger.debug(f"Could not get process output: {e}")
                    print("🔍 Could not get process output")
            
            raise TimeoutError(f"ngrok tunnel failed to start within {max_attempts} seconds")
            
        except Exception as e:
            logger.error(f"Failed to start ngrok tunnel: {e}")
            print(f"❌ Failed to start ngrok tunnel: {e}")
            
            # Better cleanup with error details
            if self.ngrok_process:
                try:
                    if self.ngrok_process.poll() is None:
                        self.ngrok_process.terminate()
                        try:
                            stdout, stderr = self.ngrok_process.communicate(timeout=5)
                            if stderr:
                                print(f"🔍 ngrok error output: {stderr}")
                        except Exception as comm_error:
                            logger.debug(f"Process communication timed out, killing: {comm_error}")
                            self.ngrok_process.kill()
                except Exception as cleanup_error:
                    logger.debug(f"Error during ngrok cleanup: {cleanup_error}")
                self.ngrok_process = None
            return None
    
    async def _get_tunnel_url(self) -> Optional[str]:
        """Get the public tunnel URL from ngrok API."""
        try:
            import urllib.request
            import json
            
            with urllib.request.urlopen(self.api_url, timeout=NgrokConstants.API_TIMEOUT) as response:
                data = json.loads(response.read().decode())
                
            tunnels = data.get("tunnels", [])
            for tunnel in tunnels:
                if tunnel.get("proto") == "https":
                    return tunnel.get("public_url")
            
            return None
            
        except Exception:
            return None
    
    async def _get_tunnel_url_with_retry(self) -> Optional[str]:
        """Get the public tunnel URL from ngrok API with retry logic."""
        max_retries = NgrokConstants.MAX_URL_RETRIES
        for retry in range(max_retries):
            try:
                import urllib.request
                import json
                
                # Try multiple API endpoints that ngrok might use
                api_endpoints = [
                    f"http://{NgrokConstants.API_HOST}:{NgrokConstants.API_PORT}{NgrokConstants.API_TUNNELS_ENDPOINT}",
                    f"http://127.0.0.1:{NgrokConstants.API_PORT}{NgrokConstants.API_TUNNELS_ENDPOINT}"
                ]
                
                for api_url in api_endpoints:
                    try:
                        with urllib.request.urlopen(api_url, timeout=NgrokConstants.EXTENDED_API_TIMEOUT) as response:
                            data = json.loads(response.read().decode())
                            
                        tunnels = data.get("tunnels", [])
                        for tunnel in tunnels:
                            if tunnel.get("proto") == "https":
                                return tunnel.get("public_url")
                        
                        # If no HTTPS tunnel found, try HTTP as fallback
                        for tunnel in tunnels:
                            if tunnel.get("proto") == "http":
                                http_url = tunnel.get("public_url")
                                if http_url:
                                    # Convert HTTP to HTTPS for TradingView compatibility
                                    return http_url.replace("http://", "https://")
                        
                    except Exception as e:
                        if retry == max_retries - 1:  # Last retry
                            print(f"🔍 API endpoint {api_url} failed: {str(e)}")
                        continue
                
                return None
                
            except Exception as e:
                if retry == max_retries - 1:  # Last retry
                    print(f"🔍 Failed to get tunnel URL (attempt {retry + 1}): {str(e)}")
                await asyncio.sleep(1)
        
        return None

    def stop_tunnel(self):
        """Stop the ngrok tunnel."""
        if self.ngrok_process:
            print("🛑 Stopping ngrok tunnel...")
            self.ngrok_process.terminate()
            try:
                self.ngrok_process.wait(timeout=NgrokConstants.PROCESS_WAIT_TIMEOUT)
            except subprocess.TimeoutExpired:
                self.ngrok_process.kill()
            self.ngrok_process = None
            self.tunnel_url = None
            print("✅ ngrok tunnel stopped")
    
    def get_tunnel_url(self) -> Optional[str]:
        """Get the current tunnel URL."""
        return self.tunnel_url
    
    def display_tunnel_info(self) -> None:
        """Display current tunnel information."""
        if self.tunnel_url:
            print("=" * 60)
            print("🌐 CURRENT NGROK TUNNEL INFO")
            print("=" * 60)
            print(f"🎯 Webhook URL: {self.tunnel_url}/webhook")
            print(f"📊 Monitor traffic: http://{NgrokConstants.API_HOST}:{NgrokConstants.API_PORT}")
            print()
            print("📋 For TradingView webhook settings:")
            print(f"   {self.tunnel_url}/webhook")
            print("=" * 60)
        else:
            print("❌ No active ngrok tunnel")
    
    def is_tunnel_active(self) -> bool:
        """Check if tunnel is currently active."""
        return self.ngrok_process is not None and self.ngrok_process.poll() is None
    
    def _check_ngrok_health(self) -> Dict[str, Any]:
        """Check ngrok health and return diagnostic information."""
        health_info = {
            "process_running": False,
            "api_accessible": False,
            "tunnel_count": 0,
            "error_messages": []
        }
        
        # Check if process is running
        if self.ngrok_process and self.ngrok_process.poll() is None:
            health_info["process_running"] = True
        else:
            health_info["error_messages"].append("ngrok process not running")
        
        # Check if API is accessible
        try:
            import urllib.request
            import json
            
            api_url = f"http://{NgrokConstants.API_HOST}:{NgrokConstants.API_PORT}{NgrokConstants.API_TUNNELS_ENDPOINT}"
            with urllib.request.urlopen(api_url, timeout=NgrokConstants.API_TIMEOUT) as response:
                data = json.loads(response.read().decode())
                health_info["api_accessible"] = True
                health_info["tunnel_count"] = len(data.get("tunnels", []))
                
        except Exception as e:
            health_info["error_messages"].append(f"API not accessible: {str(e)}")
        
        return health_info

    def __del__(self):
        """Cleanup on destruction."""
        if self.ngrok_process:
            self.stop_tunnel()


# Convenience function for easy integration
async def setup_ngrok_tunnel(port: int, config_manager=None) -> Optional[str]:
    """Setup ngrok tunnel with minimal configuration."""
    manager = NgrokManager(config_manager)
    return await manager.start_tunnel(port)


if __name__ == "__main__":
    # Test the ngrok manager
    async def test():
        manager = NgrokManager()
        url = await manager.start_tunnel(8080)
        if url:
            print(f"Tunnel URL: {url}")
            input("Press Enter to stop...")
            manager.stop_tunnel()
    
    asyncio.run(test())
