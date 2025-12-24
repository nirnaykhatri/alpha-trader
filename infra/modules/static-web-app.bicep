// ============================================================================
// Static Web App Module
// ============================================================================
// Azure Static Web Apps for hosting the trading terminal dashboard.
// Uses Free tier with Azure AD authentication.
// Proxies API requests to Container Apps.
// ============================================================================

@description('Name of the Static Web App')
param name string

@description('Azure region for the Static Web App')
param location string

@description('Resource tags')
param tags object = {}

@description('SKU for Static Web App')
@allowed(['Free', 'Standard'])
param sku string = 'Free'

@description('GitHub repository URL')
param repositoryUrl string = ''

@description('Repository branch')
param branch string = 'main'

@description('App location in repository')
param appLocation string = 'trading-terminal'

@description('Output location for build')
param outputLocation string = '.next'

@description('Container Apps FQDN for API proxy')
param containerAppsFqdn string = ''

// ============================================================================
// Static Web App Resource
// ============================================================================

resource staticWebApp 'Microsoft.Web/staticSites@2023-12-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
    tier: sku
  }
  properties: {
    repositoryUrl: repositoryUrl != '' ? repositoryUrl : null
    branch: repositoryUrl != '' ? branch : null
    buildProperties: {
      appLocation: appLocation
      outputLocation: outputLocation
      skipGithubActionWorkflowGeneration: repositoryUrl == ''
    }
    stagingEnvironmentPolicy: 'Enabled'
    allowConfigFileUpdates: true
  }
}

// ============================================================================
// Static Web App Configuration (API Proxy)
// ============================================================================

resource staticWebAppConfig 'Microsoft.Web/staticSites/config@2023-12-01' = if (containerAppsFqdn != '') {
  parent: staticWebApp
  name: 'appsettings'
  properties: {
    CONTAINER_APPS_API_URL: 'https://${containerAppsFqdn}'
  }
}

// ============================================================================
// Outputs
// ============================================================================

@description('Static Web App name')
output name string = staticWebApp.name

@description('Static Web App default hostname')
output defaultHostname string = staticWebApp.properties.defaultHostname

@description('Static Web App resource ID')
output id string = staticWebApp.id
