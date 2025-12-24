// ============================================================================
// App Configuration Access Module
// ============================================================================
// Grants RBAC access to App Configuration for a specified principal.
// Uses App Configuration Data Reader role for reading configuration.
// ============================================================================

@description('Name of the App Configuration store')
param appConfigurationName string

@description('Principal ID to grant access to')
param principalId string

// ============================================================================
// Existing Resource Reference
// ============================================================================

resource appConfiguration 'Microsoft.AppConfiguration/configurationStores@2023-03-01' existing = {
  name: appConfigurationName
}

// ============================================================================
// Role Definitions
// ============================================================================

// App Configuration Data Reader - allows reading configuration values
var appConfigDataReaderRoleId = '516239f1-63e1-4d78-a4de-a74fb236a071'

// ============================================================================
// Role Assignment
// ============================================================================

resource appConfigDataReaderRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(appConfiguration.id, principalId, appConfigDataReaderRoleId)
  scope: appConfiguration
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', appConfigDataReaderRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// Outputs
// ============================================================================

@description('Role assignment ID')
output roleAssignmentId string = appConfigDataReaderRole.id
