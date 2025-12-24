// ============================================================================
// App Configuration Module
// ============================================================================
// Azure App Configuration for SYSTEM-LEVEL configuration only.
// Supports hot-reload of settings without redeploying the application.
//
// NOTE: Bot-specific settings (DCA %, trailing %, take profit %) are stored
// in Cosmos DB per-bot. This module only contains infrastructure settings.
// ============================================================================

@description('Name of the App Configuration store')
param name string

@description('Azure region for the App Configuration store')
param location string

@description('Resource tags')
param tags object = {}

@description('SKU for App Configuration')
@allowed(['free', 'standard'])
param sku string = 'free'

@description('Environment name for configuration labels')
param environment string = 'demo'

// ============================================================================
// App Configuration Resource
// ============================================================================

resource appConfiguration 'Microsoft.AppConfiguration/configurationStores@2023-03-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
  }
  properties: {
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
}

// ============================================================================
// SYSTEM-LEVEL Configuration Values Only
// ============================================================================
// Bot-specific settings (DCA, trailing, take profit) are stored in Cosmos DB
// per-bot. Only infrastructure/system settings belong here.
// ============================================================================

// Logging Settings
resource logLevel 'Microsoft.AppConfiguration/configurationStores/keyValues@2023-03-01' = {
  parent: appConfiguration
  name: 'logging:level$${environment}'
  properties: {
    value: environment == 'live' ? 'WARNING' : 'INFO'
    contentType: 'text/plain'
    tags: {
      category: 'system'
    }
  }
}

resource logFormat 'Microsoft.AppConfiguration/configurationStores/keyValues@2023-03-01' = {
  parent: appConfiguration
  name: 'logging:format$${environment}'
  properties: {
    value: 'json'
    contentType: 'text/plain'
    tags: {
      category: 'system'
    }
  }
}

// Webhook Server Settings
resource webhookPort 'Microsoft.AppConfiguration/configurationStores/keyValues@2023-03-01' = {
  parent: appConfiguration
  name: 'api:webhook:port$${environment}'
  properties: {
    value: '8080'
    contentType: 'application/json'
    tags: {
      category: 'system'
    }
  }
}

resource webhookSecurityEnabled 'Microsoft.AppConfiguration/configurationStores/keyValues@2023-03-01' = {
  parent: appConfiguration
  name: 'api:webhook:securityEnabled$${environment}'
  properties: {
    value: 'true'
    contentType: 'application/json'
    tags: {
      category: 'system'
    }
  }
}

// Broker Base URLs (system-level, not per-bot)
resource alpacaBaseUrl 'Microsoft.AppConfiguration/configurationStores/keyValues@2023-03-01' = {
  parent: appConfiguration
  name: 'broker:alpaca:baseUrl$${environment}'
  properties: {
    value: environment == 'live' ? 'https://api.alpaca.markets' : 'https://paper-api.alpaca.markets'
    contentType: 'text/plain'
    tags: {
      category: 'system'
    }
  }
}

resource alpacaTimeout 'Microsoft.AppConfiguration/configurationStores/keyValues@2023-03-01' = {
  parent: appConfiguration
  name: 'broker:alpaca:timeout$${environment}'
  properties: {
    value: '30'
    contentType: 'application/json'
    tags: {
      category: 'system'
    }
  }
}

resource tastytradeSandbox 'Microsoft.AppConfiguration/configurationStores/keyValues@2023-03-01' = {
  parent: appConfiguration
  name: 'broker:tastytrade:isSandbox$${environment}'
  properties: {
    value: environment == 'live' ? 'false' : 'true'
    contentType: 'application/json'
    tags: {
      category: 'system'
    }
  }
}

// Monitoring Settings
resource monitoringEnabled 'Microsoft.AppConfiguration/configurationStores/keyValues@2023-03-01' = {
  parent: appConfiguration
  name: 'monitoring:enabled$${environment}'
  properties: {
    value: 'true'
    contentType: 'application/json'
    tags: {
      category: 'system'
    }
  }
}

resource healthCheckInterval 'Microsoft.AppConfiguration/configurationStores/keyValues@2023-03-01' = {
  parent: appConfiguration
  name: 'monitoring:healthCheckInterval$${environment}'
  properties: {
    value: '30'
    contentType: 'application/json'
    tags: {
      category: 'system'
    }
  }
}

// Feature Flags (system-wide controls)
resource featureMaintenanceMode 'Microsoft.AppConfiguration/configurationStores/keyValues@2023-03-01' = {
  parent: appConfiguration
  name: 'feature:maintenanceMode$${environment}'
  properties: {
    value: 'false'
    contentType: 'application/json'
    tags: {
      category: 'feature'
    }
  }
}

resource featureNewBotsEnabled 'Microsoft.AppConfiguration/configurationStores/keyValues@2023-03-01' = {
  parent: appConfiguration
  name: 'feature:newBotsEnabled$${environment}'
  properties: {
    value: 'true'
    contentType: 'application/json'
    tags: {
      category: 'feature'
    }
  }
}

// ============================================================================
// Outputs
// ============================================================================

@description('App Configuration store name')
output name string = appConfiguration.name

@description('App Configuration endpoint')
output endpoint string = appConfiguration.properties.endpoint

@description('App Configuration resource ID')
output id string = appConfiguration.id
