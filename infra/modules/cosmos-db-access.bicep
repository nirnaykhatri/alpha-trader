// ============================================================================
// Cosmos DB Access Module
// ============================================================================
// Grants RBAC access to Cosmos DB for a specified principal.
// Uses Cosmos DB Built-in Data Contributor role for read/write access.
// ============================================================================

@description('Name of the Cosmos DB account')
param cosmosDbAccountName string

@description('Principal ID to grant access to')
param principalId string

// ============================================================================
// Existing Resource Reference
// ============================================================================

resource cosmosDbAccount 'Microsoft.DocumentDB/databaseAccounts@2024-02-15-preview' existing = {
  name: cosmosDbAccountName
}

// ============================================================================
// Role Definitions
// ============================================================================

// Cosmos DB Built-in Data Contributor - allows read/write data operations
var cosmosDbDataContributorRoleId = '00000000-0000-0000-0000-000000000002'

// ============================================================================
// Role Assignment (Cosmos DB specific format)
// ============================================================================

resource cosmosDbRoleAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-02-15-preview' = {
  parent: cosmosDbAccount
  name: guid(cosmosDbAccount.id, principalId, cosmosDbDataContributorRoleId)
  properties: {
    roleDefinitionId: '${cosmosDbAccount.id}/sqlRoleDefinitions/${cosmosDbDataContributorRoleId}'
    principalId: principalId
    scope: cosmosDbAccount.id
  }
}

// ============================================================================
// Outputs
// ============================================================================

@description('Role assignment ID')
output roleAssignmentId string = cosmosDbRoleAssignment.id
