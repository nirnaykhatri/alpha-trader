using '../main.bicep'

// ============================================================================
// Demo Environment Parameters
// ============================================================================
// Parameters for the demo/paper trading environment.
// Uses free-tier services where possible.
//
// CONFIGURATION GUIDE:
// 1. Update 'location' to your preferred Azure region
// 2. Set 'githubRepoUrl' for Static Web Apps deployment
// 3. Deploy with: az deployment group create -g <resource-group> -f main.bicep -p @parameters/demo.bicepparam
//
// SUBSCRIPTION & RESOURCE GROUP:
// The subscription is determined by the resource group you deploy to.
// Create resource group first:
//   az group create --name rg-alpha-trader-demo --location <your-region> --subscription <your-subscription-id>
// ============================================================================

// ----------------------------------------------------------------------------
// Required: User Configuration
// ----------------------------------------------------------------------------

// Azure region - Choose closest to your location for lowest latency
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
// Environment Settings (defaults are recommended for demo)
// ----------------------------------------------------------------------------

param environment = 'demo'
param baseName = 'alpha-trader'
param containerImageTag = 'latest'

// Cosmos DB Free Tier - Only ONE per subscription!
// Set to false if you already have a free-tier Cosmos DB in this subscription
param enableCosmosDbFreeTier = true

// Container scaling
// minReplicas = 1 keeps bot always-on for price monitoring (trailing stops, profit-taking)
// Set to 0 if you want scale-to-zero (saves cost but misses price movements)
param minReplicas = 1
param maxReplicas = 3
