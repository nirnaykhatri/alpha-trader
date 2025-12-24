using '../main.bicep'

// ============================================================================
// Live/Production Environment Parameters
// ============================================================================
// Parameters for the live/production trading environment.
// Uses free-tier services with additional safety features.
//
// ⚠️  WARNING: This is for LIVE TRADING with real money!
// Double-check all settings before deploying.
//
// CONFIGURATION GUIDE:
// 1. Update 'location' to your preferred Azure region
// 2. Set 'githubRepoUrl' for Static Web Apps deployment
// 3. Deploy with: az deployment group create -g <resource-group> -f main.bicep -p @parameters/live.bicepparam
//
// SUBSCRIPTION & RESOURCE GROUP:
// The subscription is determined by the resource group you deploy to.
// Create resource group first:
//   az group create --name rg-alpha-trader-live --location <your-region> --subscription <your-subscription-id>
// ============================================================================

// ----------------------------------------------------------------------------
// Required: User Configuration
// ----------------------------------------------------------------------------

// Azure region - Choose closest to your broker's servers for lowest latency
// For Alpaca: eastus or westus2 recommended (US-based servers)
// Supported regions: australiaeast, brazilsouth, canadacentral, centralindia,
//   centralus, eastasia, eastus, eastus2, francecentral, germanywestcentral,
//   japaneast, koreacentral, northcentralus, northeurope, norwayeast,
//   southcentralus, southeastasia, swedencentral, switzerlandnorth, uaenorth,
//   uksouth, westeurope, westus, westus2, westus3
param location = 'eastus'

// GitHub repository URL for Static Web Apps (leave empty to skip SWA GitHub integration)
// Example: 'https://github.com/yourusername/alpha-trader'
param githubRepoUrl = ''
param githubBranch = 'main'

// ----------------------------------------------------------------------------
// Environment Settings
// ----------------------------------------------------------------------------

param environment = 'live'
param baseName = 'alpha-trader'
param containerImageTag = 'latest'

// Cosmos DB Free Tier - Only ONE per subscription!
// Set to false if you already have a free-tier Cosmos DB in this subscription
// or if you're deploying both demo AND live to same subscription
param enableCosmosDbFreeTier = true

// Container scaling - Production settings
// minReplicas = 1 is REQUIRED for live trading to ensure price monitoring
// maxReplicas = 5 allows scaling during high activity
param minReplicas = 1
param maxReplicas = 5
