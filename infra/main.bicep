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

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module app 'app.bicep' = {
  name: 'app-${environmentName}'
  scope: resourceGroup
  params: {
    environmentName: environmentName
    location: location
    principalId: principalId
    additionalCorsAllowedOrigins: additionalCorsAllowedOrigins
    tags: tags
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = resourceGroup.name
output RESOURCE_GROUP_ID string = resourceGroup.id
output AZURE_FUNCTION_APP_NAME string = app.outputs.functionAppName
output AZURE_WEB_APP_NAME string = app.outputs.webAppName
output AZURE_STORAGE_ACCOUNT_NAME string = app.outputs.storageAccountName
output AZURE_COSMOS_ENDPOINT string = app.outputs.cosmosEndpoint
output APPLICATIONINSIGHTS_CONNECTION_STRING string = app.outputs.applicationInsightsConnectionString
output AZURE_AI_SERVICES_NAME string = app.outputs.aiServicesName
output AZURE_SPEECH_ENDPOINT string = app.outputs.aiServicesEndpoint
output AZURE_OPENAI_BASE_URL string = app.outputs.openAiBaseUrl
