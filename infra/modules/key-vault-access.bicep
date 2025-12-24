// ============================================================================
// Key Vault Access Module
// ============================================================================
// Grants RBAC access to Key Vault for a specified principal (e.g., Container App).
// Uses Key Vault Secrets User role for reading secrets.
// ============================================================================

@description('Name of the Key Vault')
param keyVaultName string

@description('Principal ID to grant access to')
param principalId string

@description('Type of principal')
@allowed(['User', 'Group', 'ServicePrincipal'])
param principalType string = 'ServicePrincipal'

// ============================================================================
// Existing Resource Reference
// ============================================================================

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

// ============================================================================
// Role Definitions
// ============================================================================

// Key Vault Secrets User - allows reading secret contents
var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

// ============================================================================
// Role Assignment
// ============================================================================

resource keyVaultSecretsUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, principalId, keyVaultSecretsUserRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: principalId
    principalType: principalType
  }
}

// ============================================================================
// Outputs
// ============================================================================

@description('Role assignment ID')
output roleAssignmentId string = keyVaultSecretsUserRole.id
