// ============================================================================
// SignalR Service Module
// ============================================================================
// Azure SignalR Service for real-time WebSocket communication.
// Used to push position updates, order fills, and price changes to the UI.
// Uses Free tier (20K messages/day, 20 concurrent connections).
// ============================================================================

@description('Name of the SignalR Service')
param name string

@description('Azure region for the SignalR Service')
param location string

@description('Resource tags')
param tags object = {}

@description('SKU for SignalR Service')
@allowed(['Free_F1', 'Standard_S1', 'Premium_P1'])
param sku string = 'Free_F1'

@description('Capacity (number of units)')
@minValue(1)
@maxValue(100)
param capacity int = 1

// ============================================================================
// SignalR Service Resource
// ============================================================================

resource signalR 'Microsoft.SignalRService/signalR@2024-03-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
    tier: sku == 'Free_F1' ? 'Free' : (sku == 'Standard_S1' ? 'Standard' : 'Premium')
    capacity: capacity
  }
  kind: 'SignalR'
  properties: {
    features: [
      {
        flag: 'ServiceMode'
        value: 'Serverless' // Serverless mode for Azure Functions/Container Apps
      }
      {
        flag: 'EnableConnectivityLogs'
        value: 'True'
      }
      {
        flag: 'EnableMessagingLogs'
        value: 'True'
      }
    ]
    cors: {
      allowedOrigins: [
        '*' // Will be restricted in production via Static Web App config
      ]
    }
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
    disableAadAuth: false
  }
}

// ============================================================================
// Outputs
// ============================================================================

@description('SignalR Service name')
output name string = signalR.name

@description('SignalR Service hostname')
output hostName string = signalR.properties.hostName

@description('SignalR Service connection string')
@secure()
output connectionString string = signalR.listKeys().primaryConnectionString

@description('SignalR Service resource ID')
output id string = signalR.id
