// ============================================================================
// Monitoring Module
// ============================================================================
// Azure Monitor resources including Application Insights and alerts.
// Uses basic free tier for cost optimization.
// ============================================================================

@description('Name prefix for monitoring resources')
param name string

@description('Azure region for monitoring resources')
param location string

@description('Resource tags')
param tags object = {}

@description('Container App name to monitor')
param containerAppName string = ''

@description('Email address for alert notifications')
param alertEmailAddress string = ''

// ============================================================================
// Log Analytics Workspace (shared with Container Apps)
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
// Application Insights
// ============================================================================

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: name
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
    RetentionInDays: 30
  }
}

// ============================================================================
// Action Group (for alert notifications)
// ============================================================================

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = if (alertEmailAddress != '') {
  name: 'ag-${name}'
  location: 'Global'
  tags: tags
  properties: {
    groupShortName: 'AlphaTrader'
    enabled: true
    emailReceivers: [
      {
        name: 'Admin'
        emailAddress: alertEmailAddress
        useCommonAlertSchema: true
      }
    ]
  }
}

// ============================================================================
// Metric Alerts
// ============================================================================

// High CPU Alert
resource cpuAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = if (containerAppName != '' && alertEmailAddress != '') {
  name: 'alert-cpu-${name}'
  location: 'Global'
  tags: tags
  properties: {
    description: 'Alert when CPU usage exceeds 80%'
    severity: 2 // Warning
    enabled: true
    scopes: [
      resourceId('Microsoft.App/containerApps', containerAppName)
    ]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'HighCPU'
          metricName: 'UsageNanoCores'
          metricNamespace: 'Microsoft.App/containerApps'
          operator: 'GreaterThan'
          threshold: 800000000 // 80% of 1 core in nanocores
          timeAggregation: 'Average'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroup.id
      }
    ]
  }
}

// High Memory Alert
resource memoryAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = if (containerAppName != '' && alertEmailAddress != '') {
  name: 'alert-memory-${name}'
  location: 'Global'
  tags: tags
  properties: {
    description: 'Alert when memory usage exceeds 85%'
    severity: 2 // Warning
    enabled: true
    scopes: [
      resourceId('Microsoft.App/containerApps', containerAppName)
    ]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'HighMemory'
          metricName: 'WorkingSetBytes'
          metricNamespace: 'Microsoft.App/containerApps'
          operator: 'GreaterThan'
          threshold: 901775360 // 85% of 1GB
          timeAggregation: 'Average'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroup.id
      }
    ]
  }
}

// ============================================================================
// Outputs
// ============================================================================

@description('Application Insights name')
output name string = appInsights.name

@description('Application Insights connection string')
output connectionString string = appInsights.properties.ConnectionString

@description('Application Insights instrumentation key')
output instrumentationKey string = appInsights.properties.InstrumentationKey

@description('Log Analytics workspace ID')
output logAnalyticsWorkspaceId string = logAnalytics.id
