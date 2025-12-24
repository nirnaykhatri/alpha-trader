#!/bin/bash
# ============================================================================
# Alpha-Trader Azure Deployment Script (Bash)
# ============================================================================
# Deploys all Azure resources required for the Alpha-Trader trading bot.
#
# Usage:
#   ./deploy.sh [options]
#
# Options:
#   -e, --environment     Environment (demo|live). Default: demo
#   -l, --location        Azure region. Default: eastus
#   -S, --subscription    Azure subscription ID or name
#   -g, --resource-group  Resource group name. Default: rg-alpha-trader-{env}
#   -s, --skip-login      Skip Azure login
#   -b, --build           Build and push Docker container
#   -h, --help            Show help message
#
# Examples:
#   ./deploy.sh -e demo -l eastus
#   ./deploy.sh -e live -l westus2 -S "My Subscription"
#   ./deploy.sh -e live -l westus2 --build
# ============================================================================

set -e

# ============================================================================
# Configuration
# ============================================================================

ENVIRONMENT="demo"
LOCATION="eastus"
SUBSCRIPTION=""
RESOURCE_GROUP=""
SKIP_LOGIN=false
BUILD_CONTAINER=false
BASE_NAME="alpha-trader"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Valid Azure regions for Container Apps
VALID_REGIONS="australiaeast brazilsouth canadacentral centralindia centralus eastasia eastus eastus2 francecentral germanywestcentral japaneast koreacentral northcentralus northeurope norwayeast southcentralus southeastasia swedencentral switzerlandnorth uaenorth uksouth westeurope westus westus2 westus3"

# ============================================================================
# Colors
# ============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ============================================================================
# Helper Functions
# ============================================================================

print_step() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_success() {
    echo -e "  ${GREEN}✅ $1${NC}"
}

print_info() {
    echo -e "  ${BLUE}ℹ️  $1${NC}"
}

print_warning() {
    echo -e "  ${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "  ${RED}❌ $1${NC}"
    exit 1
}

show_help() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -e, --environment     Environment (demo|live). Default: demo"
    echo "  -l, --location        Azure region. Default: eastus"
    echo "  -S, --subscription    Azure subscription ID or name"
    echo "  -g, --resource-group  Resource group name"
    echo "  -s, --skip-login      Skip Azure login"
    echo "  -b, --build           Build and push Docker container"
    echo "  -h, --help            Show this help message"
    echo ""
    echo "Supported Regions:"
    echo "  $VALID_REGIONS"
    exit 0
}

# ============================================================================
# Parse Arguments
# ============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -l|--location)
            LOCATION="$2"
            shift 2
            ;;
        -S|--subscription)
            SUBSCRIPTION="$2"
            shift 2
            ;;
        -g|--resource-group)
            RESOURCE_GROUP="$2"
            shift 2
            ;;
        -s|--skip-login)
            SKIP_LOGIN=true
            shift
            ;;
        -b|--build)
            BUILD_CONTAINER=true
            shift
            ;;
        -h|--help)
            show_help
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            ;;
    esac
done

# Validate environment
if [[ "$ENVIRONMENT" != "demo" && "$ENVIRONMENT" != "live" ]]; then
    print_error "Invalid environment. Must be 'demo' or 'live'."
fi

# Validate region
if ! echo "$VALID_REGIONS" | grep -qw "$LOCATION"; then
    print_error "Invalid region: $LOCATION. Run with --help to see supported regions."
fi

# Set default resource group if not provided
if [[ -z "$RESOURCE_GROUP" ]]; then
    RESOURCE_GROUP="rg-${BASE_NAME}-${ENVIRONMENT}"
fi

# ============================================================================
# Banner
# ============================================================================

echo ""
echo -e "${MAGENTA}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${MAGENTA}║                                                                  ║${NC}"
echo -e "${MAGENTA}║   🚀 Alpha-Trader Azure Deployment                               ║${NC}"
echo -e "${MAGENTA}║                                                                  ║${NC}"
printf "${MAGENTA}║   Environment: %-10s  Location: %-15s     ║${NC}\n" "$ENVIRONMENT" "$LOCATION"
if [[ -n "$SUBSCRIPTION" ]]; then
    printf "${MAGENTA}║   Subscription: %-44s   ║${NC}\n" "${SUBSCRIPTION:0:44}"
fi
echo -e "${MAGENTA}║                                                                  ║${NC}"
echo -e "${MAGENTA}╚══════════════════════════════════════════════════════════════════╝${NC}"

# ============================================================================
# Prerequisites Check
# ============================================================================

print_step "Checking Prerequisites"

# Check Azure CLI
if ! command -v az &> /dev/null; then
    print_error "Azure CLI is not installed. Please install from https://aka.ms/installazurecli"
fi
print_success "Azure CLI is installed"

# Check Docker (if building container)
if [[ "$BUILD_CONTAINER" == true ]]; then
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed."
    fi
    if ! docker info &> /dev/null; then
        print_error "Docker is not running. Please start Docker."
    fi
    print_success "Docker is running"
fi

# ============================================================================
# Azure Login
# ============================================================================

if [[ "$SKIP_LOGIN" == false ]]; then
    print_step "Azure Authentication"
    
    # Check if already logged in
    if ! az account show &> /dev/null; then
        print_info "Please log in to Azure..."
        az login
    fi
    
    ACCOUNT_NAME=$(az account show --query "name" -o tsv)
    ACCOUNT_USER=$(az account show --query "user.name" -o tsv)
    print_success "Logged in as: $ACCOUNT_USER"
    print_info "Current Subscription: $ACCOUNT_NAME"
    
    # Switch subscription if specified
    if [[ -n "$SUBSCRIPTION" ]]; then
        print_info "Switching to subscription: $SUBSCRIPTION"
        az account set --subscription "$SUBSCRIPTION"
        ACCOUNT_NAME=$(az account show --query "name" -o tsv)
        ACCOUNT_ID=$(az account show --query "id" -o tsv)
        print_success "Now using: $ACCOUNT_NAME ($ACCOUNT_ID)"
    fi
fi

# ============================================================================
# Register Resource Providers
# ============================================================================

print_step "Registering Azure Resource Providers"

PROVIDERS=(
    "Microsoft.App"
    "Microsoft.ContainerRegistry"
    "Microsoft.DocumentDB"
    "Microsoft.SignalRService"
    "Microsoft.Web"
    "Microsoft.KeyVault"
    "Microsoft.AppConfiguration"
    "Microsoft.OperationalInsights"
    "Microsoft.Insights"
)

for provider in "${PROVIDERS[@]}"; do
    state=$(az provider show --namespace "$provider" --query "registrationState" -o tsv 2>/dev/null || echo "NotRegistered")
    
    if [[ "$state" != "Registered" ]]; then
        print_info "Registering $provider..."
        az provider register --namespace "$provider" --wait
    fi
done

print_success "All resource providers registered"

# ============================================================================
# Create Resource Group
# ============================================================================

print_step "Creating Resource Group"

RG_EXISTS=$(az group exists --name "$RESOURCE_GROUP")

if [[ "$RG_EXISTS" == "false" ]]; then
    az group create --name "$RESOURCE_GROUP" --location "$LOCATION" \
        --tags "Application=Alpha-Trader" "Environment=$ENVIRONMENT" > /dev/null
    print_success "Created resource group: $RESOURCE_GROUP"
else
    print_info "Resource group already exists: $RESOURCE_GROUP"
fi

# ============================================================================
# Deploy Infrastructure
# ============================================================================

print_step "Deploying Azure Infrastructure (this may take 5-10 minutes)"

TEMPLATE_FILE="$SCRIPT_DIR/main.bicep"
PARAMETERS_FILE="$SCRIPT_DIR/parameters/${ENVIRONMENT}.bicepparam"
DEPLOYMENT_NAME="alpha-trader-${ENVIRONMENT}-$(date +%Y%m%d%H%M%S)"

print_info "Starting deployment..."

if [[ -f "$PARAMETERS_FILE" ]]; then
    az deployment group create \
        --resource-group "$RESOURCE_GROUP" \
        --template-file "$TEMPLATE_FILE" \
        --parameters "@$PARAMETERS_FILE" \
        --name "$DEPLOYMENT_NAME" \
        --output none
else
    az deployment group create \
        --resource-group "$RESOURCE_GROUP" \
        --template-file "$TEMPLATE_FILE" \
        --parameters environment="$ENVIRONMENT" location="$LOCATION" \
        --name "$DEPLOYMENT_NAME" \
        --output none
fi

print_success "Infrastructure deployed successfully!"

# Get deployment outputs
LATEST_DEPLOYMENT=$(az deployment group list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv)
OUTPUTS=$(az deployment group show --resource-group "$RESOURCE_GROUP" --name "$LATEST_DEPLOYMENT" --query "properties.outputs")

# Parse outputs
ACR_NAME=$(echo "$OUTPUTS" | jq -r '.containerRegistryName.value')
ACR_LOGIN_SERVER=$(echo "$OUTPUTS" | jq -r '.containerRegistryLoginServer.value')
KEY_VAULT_NAME=$(echo "$OUTPUTS" | jq -r '.keyVaultName.value')
COSMOS_DB_ENDPOINT=$(echo "$OUTPUTS" | jq -r '.cosmosDbEndpoint.value')
CONTAINER_APP_FQDN=$(echo "$OUTPUTS" | jq -r '.containerAppFqdn.value')
CONTAINER_APP_NAME=$(echo "$OUTPUTS" | jq -r '.containerAppName.value')
WEBHOOK_URL=$(echo "$OUTPUTS" | jq -r '.webhookUrl.value')
STATIC_WEB_APP_URL=$(echo "$OUTPUTS" | jq -r '.staticWebAppUrl.value')

# Display key outputs
echo ""
echo -e "${YELLOW}📋 Deployment Outputs:${NC}"
echo -e "  Container Registry:  $ACR_LOGIN_SERVER"
echo -e "  Key Vault:           $KEY_VAULT_NAME"
echo -e "  Cosmos DB:           $COSMOS_DB_ENDPOINT"
echo -e "  Container App URL:   https://$CONTAINER_APP_FQDN"
echo -e "  Webhook URL:         $WEBHOOK_URL"
echo -e "  Trading Terminal:    https://$STATIC_WEB_APP_URL"

# ============================================================================
# Build and Push Container (Optional)
# ============================================================================

if [[ "$BUILD_CONTAINER" == true ]]; then
    print_step "Building and Pushing Docker Container"
    
    # Login to ACR
    print_info "Logging in to Container Registry..."
    az acr login --name "$ACR_NAME"
    
    # Build image
    print_info "Building Docker image..."
    cd "$REPO_ROOT"
    docker build -t "${ACR_LOGIN_SERVER}/trading-bot:latest" .
    
    # Push image
    print_info "Pushing image to registry..."
    docker push "${ACR_LOGIN_SERVER}/trading-bot:latest"
    
    print_success "Container image pushed to registry"
    
    # Update Container App
    print_info "Updating Container App with new image..."
    az containerapp update \
        --name "$CONTAINER_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --image "${ACR_LOGIN_SERVER}/trading-bot:latest"
    
    print_success "Container App updated"
fi

# ============================================================================
# Post-Deployment Instructions
# ============================================================================

print_step "Post-Deployment Steps"

echo ""
echo -e "  ${YELLOW}📝 Complete these steps to finish setup:${NC}"
echo ""
echo "  1️⃣  Add secrets to Key Vault:"
echo -e "      ${CYAN}az keyvault secret set --vault-name $KEY_VAULT_NAME --name 'alpaca-api-key' --value '<your-key>'${NC}"
echo -e "      ${CYAN}az keyvault secret set --vault-name $KEY_VAULT_NAME --name 'alpaca-secret-key' --value '<your-secret>'${NC}"
echo -e "      ${CYAN}az keyvault secret set --vault-name $KEY_VAULT_NAME --name 'webhook-secret' --value '<your-webhook-secret>'${NC}"
echo ""
echo "  2️⃣  Build and push container (if not done):"
echo -e "      ${CYAN}az acr login --name $ACR_NAME${NC}"
echo -e "      ${CYAN}docker build -t ${ACR_LOGIN_SERVER}/trading-bot:latest .${NC}"
echo -e "      ${CYAN}docker push ${ACR_LOGIN_SERVER}/trading-bot:latest${NC}"
echo ""
echo "  3️⃣  Update TradingView webhook URL:"
echo -e "      ${CYAN}$WEBHOOK_URL/<your-webhook-secret>${NC}"
echo ""
echo "  4️⃣  Access your trading terminal:"
echo -e "      ${CYAN}https://$STATIC_WEB_APP_URL${NC}"
echo ""

# ============================================================================
# Complete
# ============================================================================

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                                                  ║${NC}"
echo -e "${GREEN}║   ✅ Deployment Complete!                                        ║${NC}"
echo -e "${GREEN}║                                                                  ║${NC}"
echo -e "${GREEN}║   Estimated monthly cost: ~\$15                                  ║${NC}"
echo -e "${GREEN}║                                                                  ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo ""
