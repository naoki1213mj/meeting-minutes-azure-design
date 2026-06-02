targetScope = 'resourceGroup'

@minLength(1)
param environmentName string

param location string = resourceGroup().location

param principalId string = ''

@description('Additional exact browser origins allowed by Function App and Blob CORS. The deployed App Service frontend origin is always included. Do not use wildcard origins.')
param additionalCorsAllowedOrigins array = []

param tags object = {}

@description('Shared access key that customers enter to use the demo app. Provide at deploy time; never commit. When empty the frontend gate is disabled (local/dev only).')
@secure()
param demoAccessKey string = ''

@description('Secret injected by the frontend reverse proxy when calling the Function App, distinct from demoAccessKey. Provide at deploy time; never commit.')
@secure()
param proxySecret string = ''

param chunkSummaryDeploymentName string = 'gpt-5.4-mini'

param finalMergeDeploymentName string = 'gpt-5.4'

@minValue(1)
param chunkSummaryDeploymentCapacity int = 100

@minValue(1)
param finalMergeDeploymentCapacity int = 100

var uniqueSuffix = uniqueString(subscription().id, resourceGroup().id, environmentName)
var resourcePrefix = toLower('mm-${environmentName}-${uniqueSuffix}')
var safeStorageName = toLower('stmm${uniqueSuffix}')
var webAppName = '${resourcePrefix}-web'
var webAppOrigin = 'https://${webAppName}.azurewebsites.net'
var allowedCorsOrigins = union([
  webAppOrigin
], additionalCorsAllowedOrigins)
var commonTags = union(tags, {
  'azd-env-name': environmentName
})

var storageBlobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var storageBlobDelegatorRoleId = 'db58b8e5-c6ad-4a2a-8342-4190687cbf4a'
var storageAccountContributorRoleId = '17d1049b-9a84-46fb-8f53-869881c3d3ab'
var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageTableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
var durableTaskDataContributorRoleId = '0ad04412-c4d5-4796-b79c-f76d14c8d402'
var cosmosDataContributorRoleId = '00000000-0000-0000-0000-000000000002'
var cognitiveServicesOpenAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
var cognitiveServicesSpeechUserRoleId = 'f2dc8367-1007-4938-bd23-fe263f013447'
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'
var aiServicesName = '${resourcePrefix}-aisvc'

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${resourcePrefix}-log'
  location: location
  tags: commonTags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${resourcePrefix}-appi'
  location: location
  kind: 'web'
  tags: commonTags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

resource aiServices 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: aiServicesName
  location: location
  kind: 'AIServices'
  tags: commonTags
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: aiServicesName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource chunkSummaryModelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: aiServices
  name: chunkSummaryDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: chunkSummaryDeploymentCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.4-mini'
      version: '2026-03-17'
    }
  }
}

resource finalMergeModelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: aiServices
  name: finalMergeDeploymentName
  dependsOn: [
    chunkSummaryModelDeployment
  ]
  sku: {
    name: 'GlobalStandard'
    capacity: finalMergeDeploymentCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.4'
      version: '2026-03-05'
    }
  }
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: safeStorageName
  location: location
  tags: commonTags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    cors: {
      corsRules: [
        {
          allowedOrigins: allowedCorsOrigins
          allowedMethods: [
            'OPTIONS'
            'PUT'
          ]
          allowedHeaders: [
            'content-type'
            'x-ms-blob-type'
            'x-ms-client-request-id'
            'x-ms-date'
            'x-ms-version'
          ]
          exposedHeaders: [
            'etag'
            'x-ms-client-request-id'
            'x-ms-error-code'
            'x-ms-request-id'
            'x-ms-version'
          ]
          maxAgeInSeconds: 600
        }
      ]
    }
  }
}

resource audioContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'audio'
  properties: {
    publicAccess: 'None'
  }
}

resource transcriptContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'transcript'
  properties: {
    publicAccess: 'None'
  }
}

resource minutesContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'minutes'
  properties: {
    publicAccess: 'None'
  }
}

resource artifactsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'artifacts'
  properties: {
    publicAccess: 'None'
  }
}

resource deploymentPackageContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'deploymentpackage'
  properties: {
    publicAccess: 'None'
  }
}

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: '${resourcePrefix}-cosmos'
  location: location
  tags: commonTags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    disableLocalAuth: true
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    capabilities: [
      {
        name: 'EnableServerless'
      }
    ]
  }
}

resource cosmosDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmosAccount
  name: 'meeting-minutes'
  properties: {
    resource: {
      id: 'meeting-minutes'
    }
  }
}

resource jobsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDatabase
  name: 'jobs'
  properties: {
    resource: {
      id: 'jobs'
      partitionKey: {
        paths: [
          '/tenantId'
        ]
        kind: 'Hash'
      }
    }
  }
}

resource speakerMappingsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDatabase
  name: 'speakerMappings'
  properties: {
    resource: {
      id: 'speakerMappings'
      partitionKey: {
        paths: [
          '/tenantId'
        ]
        kind: 'Hash'
      }
    }
  }
}

resource scheduler 'Microsoft.DurableTask/schedulers@2025-11-01' = {
  name: '${resourcePrefix}-dts'
  location: location
  tags: commonTags
  properties: {
    sku: {
      name: 'Consumption'
    }
    ipAllowlist: [
      '0.0.0.0/0'
    ]
  }
}

resource taskHub 'Microsoft.DurableTask/schedulers/taskHubs@2025-11-01' = {
  parent: scheduler
  name: 'default'
}

resource functionPlan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: '${resourcePrefix}-func-prem-plan'
  location: location
  tags: commonTags
  sku: {
    name: 'EP1'
    tier: 'ElasticPremium'
    capacity: 1
  }
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2022-09-01' = {
  name: '${resourcePrefix}-funcp'
  location: location
  kind: 'functionapp,linux'
  tags: union(commonTags, {
    'azd-service-name': 'backend'
  })
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: functionPlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.13'
      alwaysOn: true
      cors: {
        allowedOrigins: allowedCorsOrigins
        supportCredentials: false
      }
      appSettings: [
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'python'
        }
        {
          name: 'AzureWebJobsStorage__accountName'
          value: storageAccount.name
        }
        {
          name: 'AzureWebJobsStorage__credential'
          value: 'managedidentity'
        }
        {
          name: 'WEBSITE_USE_PLACEHOLDER'
          value: '0'
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
        {
          name: 'ENABLE_ORYX_BUILD'
          value: 'true'
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'MEETING_MINUTES_ENV'
          value: 'azure'
        }
        {
          name: 'MEETING_MINUTES_AUTH_MODE'
          value: 'demo'
        }
        {
          name: 'MEETING_MINUTES_DEMO_TENANT_ID'
          value: 'demo-tenant'
        }
        {
          name: 'MEETING_MINUTES_DEMO_USER_ID'
          value: 'demo-user'
        }
        {
          name: 'MEETING_MINUTES_PROXY_SECRET'
          value: proxySecret
        }
        {
          name: 'MEETING_MINUTES_SPECS_DIR'
          value: '/home/site/wwwroot/specs'
        }
        {
          name: 'AZURE_STORAGE_ACCOUNT_URL'
          value: storageAccount.properties.primaryEndpoints.blob
        }
        {
          name: 'AZURE_STORAGE_CONTAINER_NAME'
          value: audioContainer.name
        }
        {
          name: 'AZURE_COSMOS_ENDPOINT'
          value: cosmosAccount.properties.documentEndpoint
        }
        {
          name: 'AZURE_COSMOS_DATABASE_NAME'
          value: cosmosDatabase.name
        }
        {
          name: 'AZURE_COSMOS_JOBS_CONTAINER_NAME'
          value: jobsContainer.name
        }
        {
          name: 'AZURE_SPEECH_ENDPOINT'
          value: aiServices.properties.endpoint
        }
        {
          name: 'AZURE_SPEECH_REQUEST_TIMEOUT_SECONDS'
          value: '480'
        }
        {
          name: 'AZURE_CONTENT_UNDERSTANDING_ENDPOINT'
          value: aiServices.properties.endpoint
        }
        {
          name: 'AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID'
          value: 'prebuilt-videoSearch'
        }
        {
          name: 'AZURE_CONTENT_UNDERSTANDING_API_VERSION'
          value: '2025-11-01'
        }
        {
          name: 'AZURE_OPENAI_BASE_URL'
          value: '${aiServices.properties.endpoint}openai/v1/'
        }
        {
          name: 'AZURE_OPENAI_DEPLOYMENT_CHUNK_SUMMARY'
          value: chunkSummaryDeploymentName
        }
        {
          name: 'AZURE_OPENAI_DEPLOYMENT_FINAL_MERGE'
          value: finalMergeDeploymentName
        }
      ]
    }
  }
}

resource functionStorageOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, functionApp.id, storageBlobDataOwnerRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataOwnerRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionStorageDelegator 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, functionApp.id, storageBlobDelegatorRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDelegatorRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionStorageAccountContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, functionApp.id, storageAccountContributorRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageAccountContributorRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionStorageQueueContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, functionApp.id, storageQueueDataContributorRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageQueueDataContributorRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionStorageTableContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, functionApp.id, storageTableDataContributorRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageTableDataContributorRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionDurableTaskRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(scheduler.id, functionApp.id, durableTaskDataContributorRoleId)
  scope: scheduler
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', durableTaskDataContributorRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource developerDurableTaskRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(scheduler.id, principalId, durableTaskDataContributorRoleId)
  scope: scheduler
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', durableTaskDataContributorRoleId)
    principalId: principalId
    principalType: 'User'
  }
}

resource functionCosmosDataRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmosAccount
  name: guid(cosmosAccount.id, functionApp.id, cosmosDataContributorRoleId)
  properties: {
    roleDefinitionId: '${cosmosAccount.id}/sqlRoleDefinitions/${cosmosDataContributorRoleId}'
    principalId: functionApp.identity.principalId
    scope: cosmosAccount.id
  }
}

resource functionOpenAiUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiServices.id, functionApp.id, cognitiveServicesOpenAiUserRoleId)
  scope: aiServices
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesOpenAiUserRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionSpeechUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiServices.id, functionApp.id, cognitiveServicesSpeechUserRoleId)
  scope: aiServices
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesSpeechUserRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionCognitiveServicesUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiServices.id, functionApp.id, cognitiveServicesUserRoleId)
  scope: aiServices
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource webPlan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: '${resourcePrefix}-web-plan'
  location: location
  kind: 'linux'
  tags: commonTags
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  properties: {
    reserved: true
  }
}

resource webApp 'Microsoft.Web/sites@2022-09-01' = {
  name: webAppName
  location: location
  kind: 'app,linux'
  tags: union(commonTags, {
    'azd-service-name': 'frontend'
  })
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: webPlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'NODE|20-lts'
      alwaysOn: true
      appCommandLine: 'npm start'
      appSettings: [
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'ApplicationInsightsAgent_EXTENSION_VERSION'
          value: '~3'
        }
        {
          name: 'VITE_API_BASE_URL'
          value: '/api'
        }
        {
          name: 'API_ORIGIN'
          value: 'https://${functionApp.properties.defaultHostName}'
        }
        {
          name: 'DEMO_ACCESS_KEY'
          value: demoAccessKey
        }
        {
          name: 'MEETING_MINUTES_PROXY_SECRET'
          value: proxySecret
        }
      ]
    }
  }
}

output functionAppName string = functionApp.name
output functionAppUrl string = 'https://${functionApp.properties.defaultHostName}'
output webAppName string = webApp.name
output webAppUrl string = 'https://${webApp.properties.defaultHostName}'
output storageAccountName string = storageAccount.name
output cosmosEndpoint string = cosmosAccount.properties.documentEndpoint
output applicationInsightsConnectionString string = appInsights.properties.ConnectionString
output aiServicesName string = aiServices.name
output aiServicesEndpoint string = aiServices.properties.endpoint
output openAiBaseUrl string = '${aiServices.properties.endpoint}openai/v1/'
