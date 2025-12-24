// ============================================================================
// Container Registry Module
// ============================================================================
// Azure Container Registry for storing Docker images for the trading bot.
// Uses Basic tier for cost efficiency in development/demo environments.
// ============================================================================

@description('Name of the Container Registry (must be globally unique)')
param name string

@description('Azure region for the Container Registry')
param location string

@description('Resource tags')
param tags object = {}

@description('SKU for the Container Registry')
@allowed(['Basic', 'Standard', 'Premium'])
param sku string = 'Basic'

@description('Enable admin user for the registry')
param adminUserEnabled bool = true

// ============================================================================
// Container Registry Resource
// ============================================================================

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
  }
  properties: {
    adminUserEnabled: adminUserEnabled
    publicNetworkAccess: 'Enabled'
    policies: {
      quarantinePolicy: {
        status: 'disabled'
      }
      trustPolicy: {
        type: 'Notary'
        status: 'disabled'
      }
      retentionPolicy: {
        days: 7
        status: sku == 'Premium' ? 'enabled' : 'disabled'
      }
    }
  }
}

// ============================================================================
// Outputs
// ============================================================================

@description('Container Registry name')
output name string = containerRegistry.name

@description('Container Registry login server')
output loginServer string = containerRegistry.properties.loginServer

@description('Container Registry resource ID')
output id string = containerRegistry.id
