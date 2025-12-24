// ============================================================================
// Alpha-Trader Azure Infrastructure - Main Orchestration
// ============================================================================
// This is the main Bicep template that orchestrates deployment of all Azure
// resources required for the Alpha-Trader trading bot.
//
// Usage:
//   az deployment group create \
//     --resource-group rg-alpha-trader-demo \
//     --template-file main.bicep \
//     --parameters environment=demo
//
// Estimated Monthly Cost: ~$15 (mostly free-tier services)
// ============================================================================

targetScope = 'resourceGroup'

// ============================================================================
// Parameters - User Configuration
// ============================================================================
// These parameters should be configured by the user before deployment.
// See infra/parameters/*.bicepparam for environment-specific values.
// ============================================================================

@description('Environment name (demo or live)')
@allowed(['demo', 'live'])
param environment string = 'demo'

@description('Azure region for all resources. Choose a region that supports Container Apps.')
@allowed([
  'australiaeast'
  'brazilsouth'
  'canadacentral'
  'centralindia'
  'centralus'
  'eastasia'
  'eastus'
  'eastus2'
  'francecentral'
  'germanywestcentral'
  'japaneast'
  'koreacentral'
  'northcentralus'
  'northeurope'
  'norwayeast'
  'southcentralus'
  'southeastasia'
  'swedencentral'
  'switzerlandnorth'
  'uaenorth'
  'uksouth'
  'westeurope'
  'westus'
  'westus2'
  'westus3'
])
param location string = 'eastus'

@description('Base name for all resources (used as prefix for resource names)')
@minLength(3)
@maxLength(20)
param baseName string = 'alpha-trader'

@description('Container image tag')
param containerImageTag string = 'latest'

@description('Enable Cosmos DB free tier (only one per subscription)')
param enableCosmosDbFreeTier bool = true

@description('Minimum number of container replicas (1 for always-on)')
@minValue(0)
@maxValue(10)
param minReplicas int = 1

@description('Maximum number of container replicas')
@minValue(1)
@maxValue(30)
param maxReplicas int = 3

@description('GitHub repository URL for Static Web Apps deployment')
param githubRepoUrl string = ''

@description('GitHub repository branch')
param githubBranch string = 'main'

// ============================================================================
// Variables
// ============================================================================

var resourcePrefix = '${baseName}-${environment}'
var tags = {
  Application: 'Alpha-Trader'
  Environment: environment
  ManagedBy: 'Bicep'
  Repository: 'alpha-trader'
}

// Unique suffix for globally unique names
var uniqueSuffix = uniqueString(resourceGroup().id, baseName, environment)

// ============================================================================
// Module: Container Registry
// ============================================================================

module containerRegistry 'modules/container-registry.bicep' = {
  name: 'deploy-container-registry'
  params: {
    name: 'cr${replace(resourcePrefix, '-', '')}${uniqueSuffix}'
    location: location
    tags: tags
    sku: 'Basic'
  }
}

// ============================================================================
// Module: Key Vault
// ============================================================================

module keyVault 'modules/key-vault.bicep' = {
  name: 'deploy-key-vault'
  params: {
    name: 'kv-${resourcePrefix}-${uniqueSuffix}'
    location: location
    tags: tags
    enableSoftDelete: environment == 'live'
    softDeleteRetentionDays: 7
  }
}

// ============================================================================
// Module: App Configuration
// ============================================================================

module appConfiguration 'modules/app-configuration.bicep' = {
  name: 'deploy-app-configuration'
  params: {
    name: 'appcs-${resourcePrefix}'
    location: location
    tags: tags
    sku: 'free'
    environment: environment
  }
}

// ============================================================================
// Module: Cosmos DB
// ============================================================================

module cosmosDb 'modules/cosmos-db.bicep' = {
  name: 'deploy-cosmos-db'
  params: {
    name: 'cosmos-${resourcePrefix}-${uniqueSuffix}'
    location: location
    tags: tags
    enableFreeTier: enableCosmosDbFreeTier
    databaseName: 'trading-bot'
    containers: [
      {
        name: 'positions'
        partitionKeyPath: '/symbol'
        defaultTtl: -1 // No TTL
      }
      {
        name: 'orders'
        partitionKeyPath: '/symbol'
        defaultTtl: 7776000 // 90 days
      }
      {
        name: 'trades'
        partitionKeyPath: '/symbol'
        defaultTtl: -1 // No TTL
      }
      {
        name: 'signals'
        partitionKeyPath: '/symbol'
        defaultTtl: 2592000 // 30 days
      }
    ]
  }
}

// ============================================================================
// Module: SignalR Service
// ============================================================================

module signalR 'modules/signalr.bicep' = {
  name: 'deploy-signalr'
  params: {
    name: 'signalr-${resourcePrefix}'
    location: location
    tags: tags
    sku: 'Free_F1'
    capacity: 1
  }
}

// ============================================================================
// Module: Container Apps
// ============================================================================

module containerApps 'modules/container-apps.bicep' = {
  name: 'deploy-container-apps'
  params: {
    name: 'ca-${resourcePrefix}'
    location: location
    tags: tags
    containerRegistryName: containerRegistry.outputs.name
    containerImageName: 'trading-bot'
    containerImageTag: containerImageTag
    minReplicas: minReplicas
    maxReplicas: maxReplicas
    keyVaultName: keyVault.outputs.name
    appConfigurationEndpoint: appConfiguration.outputs.endpoint
    cosmosDbEndpoint: cosmosDb.outputs.endpoint
    signalRConnectionString: signalR.outputs.connectionString
    environment: environment
  }
}

// ============================================================================
// Module: Static Web App (Trading Terminal)
// ============================================================================

module staticWebApp 'modules/static-web-app.bicep' = {
  name: 'deploy-static-web-app'
  params: {
    name: 'swa-${resourcePrefix}'
    location: location
    tags: tags
    sku: 'Free'
    repositoryUrl: githubRepoUrl
    branch: githubBranch
    appLocation: 'trading-terminal'
    outputLocation: '.next'
    containerAppsFqdn: containerApps.outputs.fqdn
  }
}

// ============================================================================
// Module: Monitoring
// ============================================================================

module monitoring 'modules/monitoring.bicep' = {
  name: 'deploy-monitoring'
  params: {
    name: 'appi-${resourcePrefix}'
    location: location
    tags: tags
    containerAppName: containerApps.outputs.name
    alertEmailAddress: '' // Configure in parameters file
  }
}

// ============================================================================
// RBAC: Grant Container App access to Key Vault
// ============================================================================

module keyVaultAccess 'modules/key-vault-access.bicep' = {
  name: 'deploy-key-vault-access'
  params: {
    keyVaultName: keyVault.outputs.name
    principalId: containerApps.outputs.identityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// RBAC: Grant Container App access to Cosmos DB
// ============================================================================

module cosmosDbAccess 'modules/cosmos-db-access.bicep' = {
  name: 'deploy-cosmos-db-access'
  params: {
    cosmosDbAccountName: cosmosDb.outputs.name
    principalId: containerApps.outputs.identityPrincipalId
  }
}

// ============================================================================
// RBAC: Grant Container App access to App Configuration
// ============================================================================

module appConfigAccess 'modules/app-configuration-access.bicep' = {
  name: 'deploy-app-config-access'
  params: {
    appConfigurationName: appConfiguration.outputs.name
    principalId: containerApps.outputs.identityPrincipalId
  }
}

// ============================================================================
// Outputs
// ============================================================================

@description('Container Registry name')
output containerRegistryName string = containerRegistry.outputs.name

@description('Container Registry login server')
output containerRegistryLoginServer string = containerRegistry.outputs.loginServer

@description('Key Vault name')
output keyVaultName string = keyVault.outputs.name

@description('Key Vault URI')
output keyVaultUri string = keyVault.outputs.uri

@description('App Configuration endpoint')
output appConfigurationEndpoint string = appConfiguration.outputs.endpoint

@description('Cosmos DB endpoint')
output cosmosDbEndpoint string = cosmosDb.outputs.endpoint

@description('Cosmos DB database name')
output cosmosDbDatabaseName string = cosmosDb.outputs.databaseName

@description('SignalR connection string')
@secure()
output signalRConnectionString string = signalR.outputs.connectionString

@description('Container App name')
output containerAppName string = containerApps.outputs.name

@description('Container App FQDN')
output containerAppFqdn string = containerApps.outputs.fqdn

@description('Container App webhook URL')
output webhookUrl string = 'https://${containerApps.outputs.fqdn}/webhook'

@description('Static Web App name')
output staticWebAppName string = staticWebApp.outputs.name

@description('Static Web App URL')
output staticWebAppUrl string = staticWebApp.outputs.defaultHostname

@description('Application Insights connection string')
output appInsightsConnectionString string = monitoring.outputs.connectionString

@description('Resource group name')
output resourceGroupName string = resourceGroup().name

@description('Subscription ID')
output subscriptionId string = subscription().subscriptionId

@description('Deployment location')
output deploymentLocation string = location
