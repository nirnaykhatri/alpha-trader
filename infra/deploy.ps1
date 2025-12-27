<#
.SYNOPSIS
    Deploys Alpha-Trader Azure infrastructure using Bicep templates.

.DESCRIPTION
    This script deploys all Azure resources required for the Alpha-Trader trading bot:
    - Azure Container Registry
    - Azure Container Apps
    - Azure Cosmos DB (Free Tier)
    - Azure SignalR Service (Free Tier)
    - Azure Key Vault
    - Azure App Configuration
    - Azure Static Web Apps
    - Azure Monitor / Application Insights

.PARAMETER Environment
    The deployment environment: 'demo' or 'live'. Default: demo

.PARAMETER Location
    Azure region for deployment. Default: eastus

.PARAMETER Subscription
    Azure subscription ID or name. If not specified, uses current subscription.

.PARAMETER ResourceGroup
    Resource group name. Default: rg-alpha-trader-{environment}

.PARAMETER SkipLogin
    Skip Azure CLI login (use if already logged in)

.PARAMETER BuildContainer
    Build and push Docker container after infrastructure deployment

.PARAMETER WhatIf
    Show what would be deployed without actually deploying

.EXAMPLE
    .\deploy.ps1 -Environment demo -Location eastus

.EXAMPLE
    .\deploy.ps1 -Environment live -Location westus2 -Subscription "My Subscription"

.EXAMPLE
    .\deploy.ps1 -Environment live -Location westus2 -BuildContainer

.NOTES
    Author: Alpha-Trader Team
    Requires: Azure CLI 2.50+, Docker Desktop (if using -BuildContainer)
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter()]
    [ValidateSet('demo', 'live')]
    [string]$Environment = 'demo',

    [Parameter()]
    [ValidateSet(
        'australiaeast', 'brazilsouth', 'canadacentral', 'centralindia', 'centralus',
        'eastasia', 'eastus', 'eastus2', 'francecentral', 'germanywestcentral',
        'japaneast', 'koreacentral', 'northcentralus', 'northeurope', 'norwayeast',
        'southcentralus', 'southeastasia', 'swedencentral', 'switzerlandnorth',
        'uaenorth', 'uksouth', 'westeurope', 'westus', 'westus2', 'westus3'
    )]
    [string]$Location = 'eastus',

    [Parameter()]
    [string]$Subscription = '',

    [Parameter()]
    [string]$ResourceGroup = '',

    [Parameter()]
    [switch]$SkipLogin,

    [Parameter()]
    [switch]$BuildContainer,

    [Parameter()]
    [string]$GitHubRepoUrl = ''
)

# ============================================================================
# Configuration
# ============================================================================

$ErrorActionPreference = 'Stop'
$InformationPreference = 'Continue'

$BaseName = 'alpha-trader'
$ScriptRoot = $PSScriptRoot
$RepoRoot = Split-Path $ScriptRoot -Parent

if ([string]::IsNullOrEmpty($ResourceGroup)) {
    $ResourceGroup = "rg-${BaseName}-${Environment}"
}

# ============================================================================
# Helper Functions
# ============================================================================

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "  $Message" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "  ✅ $Message" -ForegroundColor Green
}

function Write-Info {
    param([string]$Message)
    Write-Host "  ℹ️  $Message" -ForegroundColor Blue
}

function Write-Warning {
    param([string]$Message)
    Write-Host "  ⚠️  $Message" -ForegroundColor Yellow
}

function Test-AzureCli {
    try {
        $null = az version 2>$null
        return $true
    }
    catch {
        return $false
    }
}

function Test-Docker {
    try {
        $null = docker version 2>$null
        return $true
    }
    catch {
        return $false
    }
}

# ============================================================================
# Banner
# ============================================================================

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════════╗" -ForegroundColor Magenta
Write-Host "║                                                                  ║" -ForegroundColor Magenta
Write-Host "║   🚀 Alpha-Trader Azure Deployment                               ║" -ForegroundColor Magenta
Write-Host "║                                                                  ║" -ForegroundColor Magenta
Write-Host "║   Environment: $($Environment.PadRight(10))  Location: $($Location.PadRight(15))     ║" -ForegroundColor Magenta
if (-not [string]::IsNullOrEmpty($Subscription)) {
    Write-Host "║   Subscription: $($Subscription.Substring(0, [Math]::Min($Subscription.Length, 44)).PadRight(44))   ║" -ForegroundColor Magenta
}
Write-Host "║                                                                  ║" -ForegroundColor Magenta
Write-Host "╚══════════════════════════════════════════════════════════════════╝" -ForegroundColor Magenta

# ============================================================================
# Prerequisites Check
# ============================================================================

Write-Step "Checking Prerequisites"

# Check Azure CLI
if (-not (Test-AzureCli)) {
    Write-Error "Azure CLI is not installed. Please install from https://aka.ms/installazurecli"
}
Write-Success "Azure CLI is installed"

# Check Docker (if building container)
if ($BuildContainer) {
    if (-not (Test-Docker)) {
        Write-Error "Docker is not running. Please start Docker Desktop."
    }
    Write-Success "Docker is running"
}

# ============================================================================
# Azure Login
# ============================================================================

if (-not $SkipLogin) {
    Write-Step "Azure Authentication"
    
    # Check if already logged in
    $account = az account show 2>$null | ConvertFrom-Json
    
    if (-not $account) {
        Write-Info "Please log in to Azure..."
        az login
        $account = az account show | ConvertFrom-Json
    }
    
    Write-Success "Logged in as: $($account.user.name)"
    Write-Info "Current Subscription: $($account.name) ($($account.id))"
    
    # Switch subscription if specified
    if (-not [string]::IsNullOrEmpty($Subscription)) {
        Write-Info "Switching to subscription: $Subscription"
        az account set --subscription $Subscription
        $account = az account show | ConvertFrom-Json
        Write-Success "Now using: $($account.name) ($($account.id))"
    }
}

# ============================================================================
# Register Resource Providers
# ============================================================================

Write-Step "Registering Azure Resource Providers"

$providers = @(
    'Microsoft.App',
    'Microsoft.ContainerRegistry',
    'Microsoft.DocumentDB',
    'Microsoft.SignalRService',
    'Microsoft.Web',
    'Microsoft.KeyVault',
    'Microsoft.AppConfiguration',
    'Microsoft.OperationalInsights',
    'Microsoft.Insights'
)

foreach ($provider in $providers) {
    $state = az provider show --namespace $provider --query "registrationState" -o tsv 2>$null
    
    if ($state -ne 'Registered') {
        Write-Info "Registering $provider..."
        az provider register --namespace $provider --wait
    }
}

Write-Success "All resource providers registered"

# ============================================================================
# Create Resource Group
# ============================================================================

Write-Step "Creating Resource Group"

$rgExists = az group exists --name $ResourceGroup | ConvertFrom-Json

if (-not $rgExists) {
    if ($PSCmdlet.ShouldProcess($ResourceGroup, "Create Resource Group")) {
        az group create --name $ResourceGroup --location $Location --tags "Application=Alpha-Trader" "Environment=$Environment" | Out-Null
        Write-Success "Created resource group: $ResourceGroup"
    }
}
else {
    Write-Info "Resource group already exists: $ResourceGroup"
}

# ============================================================================
# Deploy Infrastructure
# ============================================================================

Write-Step "Deploying Azure Infrastructure (this may take 5-10 minutes)"

$templateFile = Join-Path $ScriptRoot "main.bicep"
$parametersFile = Join-Path $ScriptRoot "parameters" "$Environment.bicepparam"

$deploymentParams = @(
    'deployment', 'group', 'create',
    '--resource-group', $ResourceGroup,
    '--template-file', $templateFile,
    '--name', "alpha-trader-$Environment-$(Get-Date -Format 'yyyyMMddHHmmss')"
)

# Use parameters file if it exists
if (Test-Path $parametersFile) {
    $deploymentParams += '--parameters', "@$parametersFile"
}
else {
    # Use inline parameters
    $deploymentParams += '--parameters', "environment=$Environment", "location=$Location"
}

# Add GitHub repo URL if provided
if (-not [string]::IsNullOrEmpty($GitHubRepoUrl)) {
    $deploymentParams += '--parameters', "githubRepoUrl=$GitHubRepoUrl"
}

if ($WhatIf) {
    $deploymentParams += '--what-if'
    Write-Info "Running in What-If mode..."
}

Write-Info "Starting deployment..."

$deploymentOutput = az @deploymentParams 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host $deploymentOutput -ForegroundColor Red
    Write-Error "Deployment failed. See errors above."
}

if (-not $WhatIf) {
    Write-Success "Infrastructure deployed successfully!"
    
    # Parse outputs
    $outputs = az deployment group show `
        --resource-group $ResourceGroup `
        --name (az deployment group list --resource-group $ResourceGroup --query "[0].name" -o tsv) `
        --query "properties.outputs" | ConvertFrom-Json
    
    # Display key outputs
    Write-Host ""
    Write-Host "📋 Deployment Outputs:" -ForegroundColor Yellow
    Write-Host "  Container Registry:  $($outputs.containerRegistryLoginServer.value)" -ForegroundColor White
    Write-Host "  Key Vault:           $($outputs.keyVaultName.value)" -ForegroundColor White
    Write-Host "  Cosmos DB:           $($outputs.cosmosDbEndpoint.value)" -ForegroundColor White
    Write-Host "  Container App URL:   https://$($outputs.containerAppFqdn.value)" -ForegroundColor White
    Write-Host "  Webhook URL:         $($outputs.webhookUrl.value)" -ForegroundColor White
    Write-Host "  Trading Terminal:    https://$($outputs.staticWebAppUrl.value)" -ForegroundColor White
}

# ============================================================================
# Create Entra ID App Registrations
# ============================================================================

if (-not $WhatIf) {
    Write-Step "Creating Entra ID App Registrations"
    
    try {
        # Get current tenant and user info
        $currentUser = az ad signed-in-user show | ConvertFrom-Json
        $tenantId = (az account show | ConvertFrom-Json).tenantId
        
        Write-Info "Creating app registrations in tenant: $tenantId"
        
        # ========================================================================
        # 1. Create API App Registration (Backend)
        # ========================================================================
        
        Write-Info "Creating API app registration..."
        
        $apiAppName = "alpha-trader-api-$Environment"
        $apiAppIdUri = "api://alpha-trader-$Environment"
        
        # Check if API app already exists
        $existingApiApp = az ad app list --filter "displayName eq '$apiAppName'" | ConvertFrom-Json
        
        if ($existingApiApp.Count -gt 0) {
            Write-Info "API app already exists, using existing: $apiAppName"
            $apiApp = $existingApiApp[0]
            $apiAppId = $apiApp.appId
            $apiObjectId = $apiApp.id
            
            # Query existing scopes to get scope ID for permission assignment
            $existingScopes = $apiApp.api.oauth2PermissionScopes
            $accessAsUserScope = $existingScopes | Where-Object { $_.value -eq 'access_as_user' }
            if ($accessAsUserScope) {
                $scopeId = $accessAsUserScope.id
                Write-Info "Found existing access_as_user scope: $scopeId"
            } else {
                # Create scope if it doesn't exist on existing app
                $scopeId = [guid]::NewGuid().ToString()
                Write-Info "Creating access_as_user scope on existing app..."
                
                # Use Graph REST API for reliable scope creation
                $scopeBody = @{
                    api = @{
                        oauth2PermissionScopes = @(
                            @{
                                id = $scopeId
                                adminConsentDescription = "Allows the app to access the Alpha Trader API"
                                adminConsentDisplayName = "Access Alpha Trader API"
                                isEnabled = $true
                                type = "User"
                                userConsentDescription = "Allows the app to access the Alpha Trader API on your behalf"
                                userConsentDisplayName = "Access Alpha Trader API"
                                value = "access_as_user"
                            }
                        )
                    }
                } | ConvertTo-Json -Depth 5 -Compress
                
                az rest --method PATCH `
                    --uri "https://graph.microsoft.com/v1.0/applications/$apiObjectId" `
                    --headers "Content-Type=application/json" `
                    --body $scopeBody
                
                Write-Success "Created API scope: access_as_user"
            }
        }
        else {
            # Create API app
            $apiApp = az ad app create `
                --display-name $apiAppName `
                --sign-in-audience "AzureADMyOrg" `
                --identifier-uris $apiAppIdUri | ConvertFrom-Json
            
            $apiAppId = $apiApp.appId
            $apiObjectId = $apiApp.id
            
            Write-Success "Created API app: $apiAppName (App ID: $apiAppId)"
            
            # Create API scope for access using Graph REST API (more reliable than --set)
            $scopeId = [guid]::NewGuid().ToString()
            $scopeBody = @{
                api = @{
                    oauth2PermissionScopes = @(
                        @{
                            id = $scopeId
                            adminConsentDescription = "Allows the app to access the Alpha Trader API"
                            adminConsentDisplayName = "Access Alpha Trader API"
                            isEnabled = $true
                            type = "User"
                            userConsentDescription = "Allows the app to access the Alpha Trader API on your behalf"
                            userConsentDisplayName = "Access Alpha Trader API"
                            value = "access_as_user"
                        }
                    )
                }
            } | ConvertTo-Json -Depth 5 -Compress
            
            az rest --method PATCH `
                --uri "https://graph.microsoft.com/v1.0/applications/$apiObjectId" `
                --headers "Content-Type=application/json" `
                --body $scopeBody
            
            Write-Success "Created API scope: access_as_user"
        }
        
        # ========================================================================
        # 2. Create SPA App Registration (Frontend)
        # ========================================================================
        
        Write-Info "Creating SPA app registration..."
        
        $spaAppName = "alpha-trader-spa-$Environment"
        $spaRedirectUri = "https://$($outputs.staticWebAppUrl.value)"
        
        # Check if SPA app already exists
        $existingSpaApp = az ad app list --filter "displayName eq '$spaAppName'" | ConvertFrom-Json
        
        if ($existingSpaApp.Count -gt 0) {
            Write-Info "SPA app already exists, updating configuration: $spaAppName"
            $spaApp = $existingSpaApp[0]
            $spaAppId = $spaApp.appId
            $spaObjectId = $spaApp.id
            
            # Update redirect URIs for existing app (idempotent)
            $spaBody = @{
                spa = @{
                    redirectUris = @(
                        $spaRedirectUri,
                        "$spaRedirectUri/",
                        "http://localhost:3000",
                        "http://localhost:3000/"
                    )
                }
            } | ConvertTo-Json -Depth 5 -Compress
            
            az rest --method PATCH `
                --uri "https://graph.microsoft.com/v1.0/applications/$spaObjectId" `
                --headers "Content-Type=application/json" `
                --body $spaBody
            
            Write-Success "Updated SPA redirect URIs"
            
            # Check and add API permission if not already present
            $existingPermissions = az ad app permission list --id $spaObjectId | ConvertFrom-Json
            $hasApiPermission = $existingPermissions | Where-Object { $_.resourceAppId -eq $apiAppId }
            
            if (-not $hasApiPermission) {
                az ad app permission add `
                    --id $spaObjectId `
                    --api $apiAppId `
                    --api-permissions "${scopeId}=Scope"
                
                Write-Success "Added API permission to SPA"
                Write-Info "⚠️  Admin consent required: az ad app permission admin-consent --id $spaAppId"
            }
            else {
                Write-Info "API permission already configured"
            }
        }
        else {
            # Create SPA app
            $spaApp = az ad app create `
                --display-name $spaAppName `
                --sign-in-audience "AzureADMyOrg" `
                --web-redirect-uris "$spaRedirectUri" "$spaRedirectUri/" `
                --enable-id-token-issuance true `
                --enable-access-token-issuance true | ConvertFrom-Json
            
            $spaAppId = $spaApp.appId
            $spaObjectId = $spaApp.id
            
            Write-Success "Created SPA app: $spaAppName (App ID: $spaAppId)"
            
            # Configure SPA redirect URIs using Graph REST API (more reliable)
            $spaBody = @{
                spa = @{
                    redirectUris = @(
                        $spaRedirectUri,
                        "$spaRedirectUri/",
                        "http://localhost:3000",
                        "http://localhost:3000/"
                    )
                }
            } | ConvertTo-Json -Depth 5 -Compress
            
            az rest --method PATCH `
                --uri "https://graph.microsoft.com/v1.0/applications/$spaObjectId" `
                --headers "Content-Type=application/json" `
                --body $spaBody
            
            Write-Success "Configured SPA redirect URIs"
            
            # Add API permission (requires admin consent)
            az ad app permission add `
                --id $spaObjectId `
                --api $apiAppId `
                --api-permissions "${scopeId}=Scope"
            
            Write-Success "Added API permission to SPA"
            Write-Info "⚠️  Admin consent required: az ad app permission admin-consent --id $spaAppId"
        }
        
        # ========================================================================
        # 3. Update Container App with Entra ID Settings
        # ========================================================================
        
        Write-Info "Updating Container App with Entra ID settings..."
        
        # NOTE: We use ENTRA_* prefixed vars to avoid conflicts with Azure SDK's AZURE_CLIENT_ID
        # which is used for managed identity authentication. These are for Entra ID token validation.
        az containerapp update `
            --name $outputs.containerAppName.value `
            --resource-group $ResourceGroup `
            --set-env-vars `
                "ENTRA_TENANT_ID=$tenantId" `
                "ENTRA_API_CLIENT_ID=$apiAppId" `
                "ENTRA_API_AUDIENCE=$apiAppIdUri"
        
        Write-Success "Updated Container App environment variables"
        
        # ========================================================================
        # 4. Update Static Web App with Entra ID Settings
        # ========================================================================
        
        Write-Info "Updating Static Web App with Entra ID settings..."
        
        # NOTE: SPA uses ENTRA_* vars consistently with backend
        az staticwebapp appsettings set `
            --name $outputs.staticWebAppName.value `
            --resource-group $ResourceGroup `
            --setting-names `
                ENTRA_TENANT_ID="$tenantId" `
                ENTRA_SPA_CLIENT_ID="$spaAppId" `
                ENTRA_API_CLIENT_ID="$apiAppId" `
                ENTRA_API_SCOPE="$apiAppIdUri/access_as_user"
        
        Write-Success "Updated Static Web App settings"
        
        # ========================================================================
        # Display Summary
        # ========================================================================
        
        Write-Host ""
        Write-Host "📋 Entra ID Configuration:" -ForegroundColor Yellow
        Write-Host "  Tenant ID:        $tenantId" -ForegroundColor White
        Write-Host "  API App ID:       $apiAppId" -ForegroundColor White
        Write-Host "  SPA App ID:       $spaAppId" -ForegroundColor White
        Write-Host "  API Audience:     $apiAppIdUri" -ForegroundColor White
        Write-Host "  API Scope:        $apiAppIdUri/access_as_user" -ForegroundColor White
        Write-Host ""
        
    }
    catch {
        Write-Host "⚠️  Warning: Failed to create Entra ID app registrations" -ForegroundColor Yellow
        Write-Host "Error: $_" -ForegroundColor Yellow
        Write-Host "You can create these manually later or run the deployment again." -ForegroundColor Yellow
    }
}

# ============================================================================
# Build and Push Container (Optional)
# ============================================================================

if ($BuildContainer -and -not $WhatIf) {
    Write-Step "Building and Pushing Docker Container"
    
    $acrName = $outputs.containerRegistryName.value
    $acrLoginServer = $outputs.containerRegistryLoginServer.value
    
    # Login to ACR
    Write-Info "Logging in to Container Registry..."
    az acr login --name $acrName
    
    # Build image
    Write-Info "Building Docker image..."
    Push-Location $RepoRoot
    docker build -t "${acrLoginServer}/trading-bot:latest" .
    
    # Push image
    Write-Info "Pushing image to registry..."
    docker push "${acrLoginServer}/trading-bot:latest"
    Pop-Location
    
    Write-Success "Container image pushed to registry"
    
    # Update Container App
    Write-Info "Updating Container App with new image..."
    az containerapp update `
        --name $outputs.containerAppName.value `
        --resource-group $ResourceGroup `
        --image "${acrLoginServer}/trading-bot:latest"
    
    Write-Success "Container App updated"
}

# ============================================================================
# Post-Deployment Instructions
# ============================================================================

if (-not $WhatIf) {
    Write-Step "Post-Deployment Steps"
    
    $keyVaultName = $outputs.keyVaultName.value
    
    Write-Host ""
    Write-Host "  📝 Complete these steps to finish setup:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  1️⃣  Add secrets to Key Vault:" -ForegroundColor White
    Write-Host "      az keyvault secret set --vault-name $keyVaultName --name 'alpaca-api-key' --value '<your-key>'" -ForegroundColor Gray
    Write-Host "      az keyvault secret set --vault-name $keyVaultName --name 'alpaca-secret-key' --value '<your-secret>'" -ForegroundColor Gray
    Write-Host "      az keyvault secret set --vault-name $keyVaultName --name 'webhook-secret' --value '<your-webhook-secret>'" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  2️⃣  Build and push container (if not done):" -ForegroundColor White
    Write-Host "      az acr login --name $($outputs.containerRegistryName.value)" -ForegroundColor Gray
    Write-Host "      docker build -t $($outputs.containerRegistryLoginServer.value)/trading-bot:latest ." -ForegroundColor Gray
    Write-Host "      docker push $($outputs.containerRegistryLoginServer.value)/trading-bot:latest" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  3️⃣  Update TradingView webhook URL:" -ForegroundColor White
    Write-Host "      $($outputs.webhookUrl.value)/<your-webhook-secret>" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  4️⃣  Access your trading terminal:" -ForegroundColor White
    Write-Host "      https://$($outputs.staticWebAppUrl.value)" -ForegroundColor Gray
    Write-Host ""
}

# ============================================================================
# Complete
# ============================================================================

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║                                                                  ║" -ForegroundColor Green
Write-Host "║   ✅ Deployment Complete!                                        ║" -ForegroundColor Green
Write-Host "║                                                                  ║" -ForegroundColor Green
Write-Host "║   Estimated monthly cost: ~`$15                                  ║" -ForegroundColor Green
Write-Host "║                                                                  ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
