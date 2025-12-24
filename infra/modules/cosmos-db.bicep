// ============================================================================
// Cosmos DB Module
// ============================================================================
// Azure Cosmos DB NoSQL database for storing trading data.
// Uses Free Tier (1,000 RU/s + 25GB) for cost optimization.
//
// Containers:
//   - positions: Active positions with embedded tracking/DCA metadata
//   - orders: Order history with 90-day TTL
//   - trades: Completed trades
//   - signals: Trading signals with 30-day TTL
// ============================================================================

@description('Name of the Cosmos DB account')
param name string

@description('Azure region for the Cosmos DB account')
param location string

@description('Resource tags')
param tags object = {}

@description('Enable free tier (only one per subscription)')
param enableFreeTier bool = true

@description('Name of the database')
param databaseName string = 'trading-bot'

@description('Container configurations')
param containers array = []

// ============================================================================
// Cosmos DB Account
// ============================================================================

resource cosmosDbAccount 'Microsoft.DocumentDB/databaseAccounts@2024-02-15-preview' = {
  name: name
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    enableFreeTier: enableFreeTier
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    capabilities: [
      {
        name: 'EnableServerless'
      }
    ]
    publicNetworkAccess: 'Enabled'
    enableAutomaticFailover: false
    enableMultipleWriteLocations: false
    disableKeyBasedMetadataWriteAccess: false
  }
}

// ============================================================================
// Database
// ============================================================================

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-02-15-preview' = {
  parent: cosmosDbAccount
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
  }
}

// ============================================================================
// Containers
// ============================================================================

resource cosmosContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = [for container in containers: {
  parent: database
  name: container.name
  properties: {
    resource: {
      id: container.name
      partitionKey: {
        paths: [container.partitionKeyPath]
        kind: 'Hash'
        version: 2
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          {
            path: '/symbol/?'
          }
          {
            path: '/broker/?'
          }
          {
            path: '/status/?'
          }
          {
            path: '/createdAt/?'
          }
          {
            path: '/type/?'
          }
        ]
        excludedPaths: [
          {
            path: '/dcaMetadata/*'
          }
          {
            path: '/tracking/*'
          }
          {
            path: '/dcaOrders/*'
          }
          {
            path: '/"_etag"/?'
          }
        ]
        compositeIndexes: [
          [
            {
              path: '/symbol'
              order: 'ascending'
            }
            {
              path: '/status'
              order: 'ascending'
            }
          ]
          [
            {
              path: '/symbol'
              order: 'ascending'
            }
            {
              path: '/createdAt'
              order: 'descending'
            }
          ]
        ]
      }
      defaultTtl: container.defaultTtl
    }
  }
}]

// ============================================================================
// Outputs
// ============================================================================

@description('Cosmos DB account name')
output name string = cosmosDbAccount.name

@description('Cosmos DB endpoint')
output endpoint string = cosmosDbAccount.properties.documentEndpoint

@description('Cosmos DB database name')
output databaseName string = database.name

@description('Cosmos DB resource ID')
output id string = cosmosDbAccount.id
