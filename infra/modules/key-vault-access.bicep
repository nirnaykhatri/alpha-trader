// ============================================================================
// Key Vault Access Module
// ============================================================================
// Grants RBAC access to Key Vault for a specified principal (e.g., Container App).
//
// Roles Assigned:
//   - Key Vault Secrets User: Read-only access for reading secrets (config)
//   - Key Vault Secrets Officer: Read/Write/Delete for UI-added broker credentials
//
// Security Note: Single backend identity uses Secrets Officer to manage
// dynamically added broker credentials while maintaining read access for static config.
// ============================================================================

@description('Name of the Key Vault')
param keyVaultName string

@description('Principal ID to grant access to')
param principalId string

@description('Type of principal')
@allowed(['User', 'Group', 'ServicePrincipal'])
param principalType string = 'ServicePrincipal'

@description('Grant Secrets Officer role for write/delete operations (required for UI-added brokers). Defaults to false for least-privilege; explicitly set to true in deployments that need credential management.')
param grantSecretsOfficer bool = false

// ============================================================================
// Existing Resource Reference
// ============================================================================

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

// ============================================================================
// Role Definitions
// ============================================================================

// Key Vault Secrets User - allows reading secret contents (read-only)
var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

// Key Vault Secrets Officer - allows create/update/delete of secrets
// Required for: UI-added broker credentials, runtime credential management
var keyVaultSecretsOfficerRoleId = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'

// ============================================================================
// Role Assignments
// ============================================================================

// Read-only access for all config secrets
resource keyVaultSecretsUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, principalId, keyVaultSecretsUserRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: principalId
    principalType: principalType
  }
}

// Write/Delete access for UI-added broker credentials
resource keyVaultSecretsOfficerRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (grantSecretsOfficer) {
  name: guid(keyVault.id, principalId, keyVaultSecretsOfficerRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsOfficerRoleId)
    principalId: principalId
    principalType: principalType
  }
}

// ============================================================================
// Outputs
// ============================================================================

@description('Secrets User role assignment ID')
output secretsUserRoleAssignmentId string = keyVaultSecretsUserRole.id

@description('Secrets Officer role assignment ID (empty if not granted)')
output secretsOfficerRoleAssignmentId string = grantSecretsOfficer ? keyVaultSecretsOfficerRole.id : ''

// Legacy output for backward compatibility
@description('Role assignment ID (deprecated: use secretsUserRoleAssignmentId)')
output roleAssignmentId string = keyVaultSecretsUserRole.id
