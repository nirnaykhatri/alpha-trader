// ============================================================================
// Key Vault Module
// ============================================================================
// Azure Key Vault for secure storage of secrets (API keys, passwords).
// Uses Managed Identity for access - no credentials stored in code.
// ============================================================================

@description('Name of the Key Vault')
param name string

@description('Azure region for the Key Vault')
param location string

@description('Resource tags')
param tags object = {}

@description('Enable soft delete for the vault')
param enableSoftDelete bool = true

@description('Soft delete retention period in days')
@minValue(7)
@maxValue(90)
param softDeleteRetentionDays int = 7

@description('Enable purge protection (cannot be disabled once enabled)')
param enablePurgeProtection bool = false

// ============================================================================
// Key Vault Resource
// ============================================================================

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: enableSoftDelete
    softDeleteRetentionInDays: softDeleteRetentionDays
    enablePurgeProtection: enablePurgeProtection ? true : null
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
}

// ============================================================================
// Outputs
// ============================================================================

@description('Key Vault name')
output name string = keyVault.name

@description('Key Vault URI')
output uri string = keyVault.properties.vaultUri

@description('Key Vault resource ID')
output id string = keyVault.id
