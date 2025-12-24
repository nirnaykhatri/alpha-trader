# Deprecated ngrok Scripts

These scripts were used for local development with ngrok tunneling.

## Deprecation Notice

**These scripts are deprecated and no longer maintained.**

With the Azure cloud migration, ngrok is no longer needed because:
- The trading bot runs on Azure Container Apps with a public HTTPS endpoint
- TradingView webhooks connect directly to the Azure URL
- No local tunneling is required

## Migration Path

If you're still using ngrok locally:
1. Follow the [Azure Deployment Guide](../../docs/AZURE_DEPLOYMENT.md)
2. Deploy the bot to Azure Container Apps
3. Update TradingView webhook URL to your Azure endpoint

## Files in this Directory

| File | Original Purpose |
|------|-----------------|
| `start_ngrok_standalone.py` | Start ngrok tunnel independently |
| `start_ngrok_standalone.bat` | Windows batch script for ngrok |
| `start_bot_with_ngrok.bat` | Start bot with ngrok tunnel |
| `start_bot_no_ngrok.py` | Start bot without ngrok |
| `start_bot_no_ngrok.bat` | Windows batch script without ngrok |
| `setup_ngrok_auth.py` | Configure ngrok authentication |
| `check_ngrok_status.py` | Check ngrok tunnel status |
| `get_webhook_url.py` | Get current webhook URL |
| `setup_alternative_tunnels.py` | Setup alternative tunnel services |

## If You Still Need Local Tunneling

For local development testing, you can use the Azure Static Web Apps CLI:

```bash
# Install SWA CLI
npm install -g @azure/static-web-apps-cli

# Run with proxy to local bot
swa start http://localhost:8080
```

Or use the legacy ngrok files at your own discretion (unsupported).
