#!/usr/bin/env python3
"""
Helper script to set up ngrok authentication token.
"""

import os
import sys
import yaml
from pathlib import Path

def setup_ngrok_auth():
    """Interactive setup for ngrok authentication."""
    
    print("🔧 ngrok Authentication Setup")
    print("=" * 50)
    print()
    print("ngrok now requires a free account for tunneling.")
    print("Don't worry - it's completely free and takes 2 minutes!")
    print()
    print("📋 Steps to get your free ngrok token:")
    print("1. Go to: https://dashboard.ngrok.com/signup")
    print("2. Sign up for a free account (email + password)")
    print("3. Go to: https://dashboard.ngrok.com/get-started/your-authtoken")
    print("4. Copy your authtoken")
    print("5. Paste it below")
    print()
    
    # Get token from user
    while True:
        token = input("🔑 Enter your ngrok authtoken (or 'skip' to continue without): ").strip()
        
        if token.lower() == 'skip':
            print("⚠️  Skipping ngrok setup. Bot will run without webhook tunneling.")
            return False
            
        if not token:
            print("❌ Please enter a valid token or 'skip'")
            continue
            
        if len(token) < 20:
            print("❌ Token seems too short. Please check and try again.")
            continue
            
        break
    
    # Offer configuration options
    print()
    print("📝 How would you like to store the token?")
    print("1. Environment variable (recommended for development)")
    print("2. config.yaml file (permanent)")
    print("3. Both")
    
    while True:
        choice = input("Choose option (1/2/3): ").strip()
        if choice in ['1', '2', '3']:
            break
        print("❌ Please enter 1, 2, or 3")
    
    success = False
    
    # Set environment variable
    if choice in ['1', '3']:
        try:
            os.environ['NGROK_AUTH_TOKEN'] = token
            print("✅ Environment variable NGROK_AUTH_TOKEN set for this session")
            
            # Create a batch file to set it permanently on Windows
            if sys.platform == "win32":
                batch_content = f"""@echo off
echo Setting ngrok auth token...
setx NGROK_AUTH_TOKEN "{token}"
echo ✅ ngrok auth token set permanently
echo You may need to restart your terminal/IDE for it to take effect
pause
"""
                with open("set_ngrok_token.bat", "w") as f:
                    f.write(batch_content)
                print("📄 Created 'set_ngrok_token.bat' - run it to set token permanently")
            
            success = True
        except Exception as e:
            print(f"❌ Failed to set environment variable: {e}")
    
    # Add to config.yaml
    if choice in ['2', '3']:
        try:
            config_path = Path("config.yaml")
            
            # Load existing config or create new
            config = {}
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f) or {}
            
            # Add ngrok section
            if 'ngrok' not in config:
                config['ngrok'] = {}
            config['ngrok']['auth_token'] = token
            
            # Write back to file
            with open(config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            
            print(f"✅ Added auth token to {config_path}")
            success = True
            
        except Exception as e:
            print(f"❌ Failed to update config.yaml: {e}")
    
    if success:
        print()
        print("🎉 ngrok authentication setup complete!")
        print("🚀 You can now run your trading bot with webhook support")
        print()
        print("🔗 Free ngrok features:")
        print("   • 1 tunnel at a time")
        print("   • Random URL each restart") 
        print("   • Up to 20 connections/minute")
        print("   • Perfect for development and testing!")
    
    return success

def test_ngrok_auth():
    """Test if ngrok authentication is working."""
    print()
    print("🧪 Testing ngrok authentication...")
    
    # Check environment variable
    env_token = os.environ.get('NGROK_AUTH_TOKEN')
    if env_token:
        print(f"✅ Found NGROK_AUTH_TOKEN in environment")
        return True
    
    # Check config.yaml
    try:
        config_path = Path("config.yaml")
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
                
            if config.get('ngrok', {}).get('auth_token'):
                print("✅ Found ngrok.auth_token in config.yaml")
                return True
    except Exception as e:
        print(f"⚠️  Error reading config.yaml: {e}")
    
    print("❌ No ngrok auth token found")
    return False

if __name__ == "__main__":
    print("🤖 Trading Bot - ngrok Setup Helper")
    print("=" * 40)
    
    # Check if already configured
    if test_ngrok_auth():
        print("🎉 ngrok authentication is already configured!")
        print("You're ready to run the trading bot with webhook support.")
    else:
        setup_ngrok_auth()
