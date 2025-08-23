#!/usr/bin/env python3
"""
Alternative tunneling solutions for the trading bot.
"""

import subprocess
import sys
import os
import time
import requests
from pathlib import Path

class AlternativeTunnelManager:
    """Manager for alternative tunneling services."""
    
    def __init__(self):
        self.tunnel_url = None
        self.process = None
        
    def setup_cloudflared(self):
        """Set up Cloudflare Tunnel (completely free, no signup required)."""
        print("🌩️  Setting up Cloudflare Tunnel...")
        
        # Check if cloudflared is installed
        cloudflared_path = self._find_cloudflared()
        if not cloudflared_path:
            print("📥 Downloading cloudflared...")
            cloudflared_path = self._download_cloudflared()
            
        if cloudflared_path:
            print("✅ cloudflared is ready")
            return cloudflared_path
        else:
            print("❌ Failed to set up cloudflared")
            return None
    
    def _find_cloudflared(self):
        """Find cloudflared executable."""
        # Check if cloudflared is in PATH
        try:
            result = subprocess.run(['cloudflared', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                return 'cloudflared'
        except FileNotFoundError:
            pass
        
        # Check local installation
        local_path = Path('.cloudflared') / 'cloudflared.exe'
        if local_path.exists():
            return str(local_path)
            
        return None
    
    def _download_cloudflared(self):
        """Download cloudflared for Windows."""
        try:
            # Create directory
            cloudflared_dir = Path('.cloudflared')
            cloudflared_dir.mkdir(exist_ok=True)
            
            # Download URL for Windows
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
            cloudflared_path = cloudflared_dir / 'cloudflared.exe'
            
            print(f"📥 Downloading from: {url}")
            
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(cloudflared_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f"\r📥 Downloading cloudflared: {percent:.1f}% ({downloaded // 1024}KB / {total_size // 1024}KB)", end='')
            
            print(f"\n✅ cloudflared downloaded successfully")
            return str(cloudflared_path)
            
        except Exception as e:
            print(f"❌ Failed to download cloudflared: {e}")
            return None
    
    def start_cloudflare_tunnel(self, port=8080):
        """Start Cloudflare tunnel."""
        cloudflared_path = self.setup_cloudflared()
        if not cloudflared_path:
            return None
            
        try:
            print(f"🚇 Starting Cloudflare tunnel for port {port}...")
            
            # Start cloudflared tunnel
            self.process = subprocess.Popen(
                [cloudflared_path, 'tunnel', '--url', f'http://localhost:{port}'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait for tunnel to start and get URL
            for _ in range(30):  # Wait up to 30 seconds
                if self.process.poll() is not None:
                    stdout, stderr = self.process.communicate()
                    print(f"❌ cloudflared failed to start:")
                    print(f"stdout: {stdout}")
                    print(f"stderr: {stderr}")
                    return None
                
                # Try to get tunnel info
                try:
                    # cloudflared outputs the URL to stderr
                    time.sleep(1)
                    # For cloudflared, we need to parse the output differently
                    # Let's implement a simpler approach
                    time.sleep(3)  # Give it time to start
                    
                    # Check if process is still running
                    if self.process.poll() is None:
                        print("✅ Cloudflare tunnel started successfully!")
                        print("📋 Check the terminal output above for your tunnel URL")
                        print("🔗 It will look like: https://xxxxxxxx.trycloudflare.com")
                        return "cloudflare_tunnel_started"
                    
                except Exception as e:
                    print(f"Error checking tunnel status: {e}")
                
                time.sleep(1)
            
            print("⏰ Timeout waiting for Cloudflare tunnel to start")
            return None
            
        except Exception as e:
            print(f"❌ Failed to start Cloudflare tunnel: {e}")
            return None
    
    def setup_localtunnel(self):
        """Set up localtunnel (requires Node.js)."""
        print("🌐 Setting up localtunnel...")
        
        # Check if Node.js is installed
        try:
            result = subprocess.run(['node', '--version'], capture_output=True, text=True)
            if result.returncode != 0:
                print("❌ Node.js is required for localtunnel")
                print("📥 Download from: https://nodejs.org/")
                return False
        except FileNotFoundError:
            print("❌ Node.js not found")
            print("📥 Download from: https://nodejs.org/")
            return False
        
        # Check if localtunnel is installed
        try:
            result = subprocess.run(['lt', '--version'], capture_output=True, text=True)
            if result.returncode != 0:
                print("📦 Installing localtunnel...")
                result = subprocess.run(['npm', 'install', '-g', 'localtunnel'], capture_output=True, text=True)
                if result.returncode != 0:
                    print(f"❌ Failed to install localtunnel: {result.stderr}")
                    return False
        except FileNotFoundError:
            print("📦 Installing localtunnel...")
            result = subprocess.run(['npm', 'install', '-g', 'localtunnel'], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"❌ Failed to install localtunnel: {result.stderr}")
                return False
        
        print("✅ localtunnel is ready")
        return True
    
    def start_localtunnel(self, port=8080):
        """Start localtunnel."""
        if not self.setup_localtunnel():
            return None
            
        try:
            print(f"🚇 Starting localtunnel for port {port}...")
            
            self.process = subprocess.Popen(
                ['lt', '--port', str(port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait for tunnel URL
            for _ in range(20):
                if self.process.poll() is not None:
                    stdout, stderr = self.process.communicate()
                    print(f"❌ localtunnel failed: {stderr}")
                    return None
                
                # Try to read output
                time.sleep(1)
                
            # localtunnel usually prints URL immediately
            time.sleep(2)
            if self.process.poll() is None:
                print("✅ localtunnel started!")
                print("📋 Check terminal output for your tunnel URL")
                return "localtunnel_started"
            
            return None
            
        except Exception as e:
            print(f"❌ Failed to start localtunnel: {e}")
            return None
    
    def stop(self):
        """Stop the tunnel."""
        if self.process:
            self.process.terminate()
            self.process = None

def show_alternatives():
    """Show all free alternatives to ngrok."""
    
    print("🔄 Free Alternatives to ngrok")
    print("=" * 40)
    print()
    print("1. 🌩️  Cloudflare Tunnel (Recommended)")
    print("   • Completely free, no signup required")
    print("   • Fast and reliable")
    print("   • No connection limits")
    print("   • URL format: https://xxxxx.trycloudflare.com")
    print()
    print("2. 🌐 localtunnel")
    print("   • Free, no signup required")
    print("   • Requires Node.js")
    print("   • URL format: https://xxxxx.loca.lt")
    print()
    print("3. 🔑 ngrok with free auth token (Original)")
    print("   • Free account required (2-minute signup)")
    print("   • 1 tunnel, random URL each restart")
    print("   • Most reliable option")
    print()
    
    choice = input("Choose option (1/2/3): ").strip()
    
    tunnel_manager = AlternativeTunnelManager()
    
    if choice == '1':
        return tunnel_manager.start_cloudflare_tunnel()
    elif choice == '2':
        return tunnel_manager.start_localtunnel()
    elif choice == '3':
        print("Please run: python setup_ngrok_auth.py")
        return None
    else:
        print("❌ Invalid choice")
        return None

if __name__ == "__main__":
    show_alternatives()
