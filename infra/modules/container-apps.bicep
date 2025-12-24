// ============================================================================
// Container Apps Module
// ============================================================================
// Azure Container Apps for running the trading bot.
// Configured for always-on operation (min replicas = 1) to support
// continuous price monitoring for trailing stops and profit taking.
// ============================================================================

@description('Name of the Container App')
param name string

@description('Azure region for the Container App')
param location string

@description('Resource tags')
param tags object = {}

@description('Container Registry name')
param containerRegistryName string

@description('Container image name')
param containerImageName string = 'trading-bot'

@description('Container image tag')
param containerImageTag string = 'latest'

@description('Minimum number of replicas')
@minValue(0)
@maxValue(10)
param minReplicas int = 1

@description('Maximum number of replicas')
@minValue(1)
@maxValue(30)
param maxReplicas int = 3

@description('Key Vault name for secrets')
param keyVaultName string

@description('App Configuration endpoint')
param appConfigurationEndpoint string

@description('Cosmos DB endpoint')
param cosmosDbEndpoint string

@description('SignalR connection string')
@secure()
param signalRConnectionString string

@description('Environment name')
param environment string = 'demo'

// ============================================================================
// Existing Resources
// ============================================================================

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: containerRegistryName
}

// ============================================================================
// Log Analytics Workspace
// ============================================================================

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: 'log-${name}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

// ============================================================================
// Container Apps Environment
// ============================================================================

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${name}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    zoneRedundant: false
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

// ============================================================================
// Container App
// ============================================================================

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: {
        external: true
        targetPort: 8080
        transport: 'http'
        allowInsecure: false
        corsPolicy: {
          allowedOrigins: ['*']
          allowedMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
          allowedHeaders: ['*']
          maxAge: 86400
        }
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          identity: 'system'
        }
      ]
      secrets: [
        {
          name: 'signalr-connection-string'
          value: signalRConnectionString
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'trading-bot'
          image: '${containerRegistry.properties.loginServer}/${containerImageName}:${containerImageTag}'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'TRADING_BOT_ENV'
              value: environment
            }
            {
              name: 'AZURE_KEY_VAULT_NAME'
              value: keyVaultName
            }
            {
              name: 'AZURE_APP_CONFIGURATION_ENDPOINT'
              value: appConfigurationEndpoint
            }
            {
              name: 'AZURE_COSMOS_DB_ENDPOINT'
              value: cosmosDbEndpoint
            }
            {
              name: 'AZURE_SIGNALR_CONNECTION_STRING'
              secretRef: 'signalr-connection-string'
            }
            {
              name: 'AZURE_CLIENT_ID'
              value: '' // Will be set by Managed Identity
            }
            {
              name: 'ASPNETCORE_URLS'
              value: 'http://+:8080'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8080
                scheme: 'HTTP'
              }
              initialDelaySeconds: 30
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/ready'
                port: 8080
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '100'
              }
            }
          }
        ]
      }
    }
  }
}

// ============================================================================
// Grant Container App access to Container Registry
// ============================================================================

// AcrPull role
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, containerApp.id, acrPullRoleId)
  scope: containerRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// Outputs
// ============================================================================

@description('Container App name')
output name string = containerApp.name

@description('Container App FQDN')
output fqdn string = containerApp.properties.configuration.ingress.fqdn

@description('Container App identity principal ID')
output identityPrincipalId string = containerApp.identity.principalId

@description('Container App resource ID')
output id string = containerApp.id

@description('Container Apps Environment ID')
output environmentId string = containerAppsEnvironment.id
