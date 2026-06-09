targetScope = 'subscription'

@minLength(1)
param environmentName string

param location string = deployment().location

param principalId string = ''

@description('Additional exact browser origins allowed by Function App and Blob CORS. Keep empty for the deployed App Service frontend only; do not use wildcard origins.')
param additionalCorsAllowedOrigins array = []

param tags object = {
  app: 'meeting-minutes-azure-design'
  env: environmentName
  owner: 'example-owner'
}

@description('Shared access key customers enter to use the demo app. Provide via the AZURE_DEMO_ACCESS_KEY environment variable; never commit.')
@secure()
param demoAccessKey string = ''

@description('Secret used by the frontend reverse proxy to call the Function App. Provide via the AZURE_PROXY_SECRET environment variable; never commit.')
@secure()
param proxySecret string = ''

@description('When true, new transcript/minutes/visual artifacts are written to a private artifact Storage account through Private Endpoint.')
@allowed([
  'true'
  'false'
])
param enablePrivateArtifacts string = 'false'

@description('When true, create a Cosmos DB Private Endpoint and private DNS link while keeping public access enabled unless lockDownCosmosPublicAccess is also true.')
@allowed([
  'true'
  'false'
])
param enableCosmosPrivateEndpoint string = 'false'

@description('When true, disable Cosmos DB public network access after private connectivity has been validated.')
@allowed([
  'true'
  'false'
])
param lockDownCosmosPublicAccess string = 'false'

param vnetAddressPrefix string = '10.42.0.0/24'

param functionIntegrationSubnetPrefix string = '10.42.0.0/27'

param privateEndpointSubnetPrefix string = '10.42.0.32/27'

@description('Microsoft Foundry project child resource name for the new Foundry portal.')
param foundryProjectName string = 'minutes-studio'

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

var enablePrivateArtifactsBool = toLower(enablePrivateArtifacts) == 'true'
var enableCosmosPrivateEndpointBool = toLower(enableCosmosPrivateEndpoint) == 'true'
var lockDownCosmosPublicAccessBool = toLower(lockDownCosmosPublicAccess) == 'true'

module app 'app.bicep' = {
  name: 'app-${environmentName}'
  scope: resourceGroup
  params: {
    environmentName: environmentName
    location: location
    principalId: principalId
    additionalCorsAllowedOrigins: additionalCorsAllowedOrigins
    tags: tags
    demoAccessKey: demoAccessKey
    proxySecret: proxySecret
    enablePrivateArtifacts: enablePrivateArtifactsBool
    enableCosmosPrivateEndpoint: enableCosmosPrivateEndpointBool
    lockDownCosmosPublicAccess: lockDownCosmosPublicAccessBool
    vnetAddressPrefix: vnetAddressPrefix
    functionIntegrationSubnetPrefix: functionIntegrationSubnetPrefix
    privateEndpointSubnetPrefix: privateEndpointSubnetPrefix
    foundryProjectName: foundryProjectName
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = resourceGroup.name
output RESOURCE_GROUP_ID string = resourceGroup.id
output AZURE_FUNCTION_APP_NAME string = app.outputs.functionAppName
output AZURE_WEB_APP_NAME string = app.outputs.webAppName
output AZURE_STORAGE_ACCOUNT_NAME string = app.outputs.storageAccountName
output AZURE_ARTIFACT_STORAGE_ACCOUNT_NAME string = app.outputs.artifactStorageAccountName
output AZURE_COSMOS_ENDPOINT string = app.outputs.cosmosEndpoint
output APPLICATIONINSIGHTS_CONNECTION_STRING string = app.outputs.applicationInsightsConnectionString
output AZURE_AI_SERVICES_NAME string = app.outputs.aiServicesName
output AZURE_SPEECH_ENDPOINT string = app.outputs.aiServicesEndpoint
output AZURE_OPENAI_BASE_URL string = app.outputs.openAiBaseUrl
output AZURE_FOUNDRY_PROJECT_NAME string = app.outputs.foundryProjectName
output AZURE_FOUNDRY_PROJECT_ID string = app.outputs.foundryProjectId
