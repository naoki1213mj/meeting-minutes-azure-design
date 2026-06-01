# Azure Deployment Plan

> **Status:** Dev MVP deployed / production hardening pending

Last updated: 2026-06-01T21:16:36+09:00

---

## 1. Project Overview

**Goal:** Azure上で録音済み音声から話者分離付き文字起こしと議事録を生成するdev MVPを構築する。

**Current path:** Existing deployed MVP. 次の主作業は本番化ハードニング（Microsoft Entra ID / Easy Auth、認可、代表音声回帰、性能基準）。

---

## 2. Requirements and Current Environment

| Attribute | Value |
|-----------|-------|
| Classification | Development / POC |
| Scale | Small initial MVP |
| Budget | Balanced |
| **Subscription** | `<subscription-name>` (`<subscription-id>`) |
| **Tenant** | `<tenant-id>` |
| **Resource group** | `<resource-group>` |
| **Location** | `westus3` |
| **Production readiness** | Not production-ready until Entra ID/Easy Auth and user authorization are enforced |

---

## 3. Components Detected

| Component | Type | Technology | Path |
|-----------|------|------------|------|
| Backend API and workflow | API / Worker | Python 3.13, Azure Functions Premium EP1, Durable Functions | `backend/` |
| Frontend | Frontend | React, TypeScript, Vite, Azure App Service | `frontend/` |
| Infrastructure | IaC | Bicep, Azure Developer CLI | `infra/`, `azure.yaml` |
| Schemas | Contract | JSON Schema 2020-12, OpenAPI 3.1 | `specs/` |

---

## 4. Recipe Selection

**Selected:** AZD + Bicep

**Rationale:** The project standardizes on Bicep and Azure Developer CLI. Deployment execution followed validation and deploy workflows; direct ad-hoc resource creation should be avoided except for documented repair/hardening steps.

---

## 5. Architecture

**Stack:** Azure App Service frontend + Azure Functions Premium backend

### Service Mapping

| Component | Azure Service | SKU / Mode | Current state |
|-----------|---------------|------------|---------------|
| Frontend | Azure App Service | Linux App Service | Deployed: `<web-app-name>` |
| Backend API | Azure Functions | Premium EP1, Python 3.13 | Deployed: `<function-app-name>` |
| Workflow | Durable Functions | Durable Task Scheduler | Deployed; v1 `function.json` wrappers |
| Audio/artifacts | Azure Blob Storage | Standard | Deployed |
| Job metadata | Azure Cosmos DB for NoSQL | Serverless/autoscale per template | Deployed |
| Speech transcription | Azure Speech in Foundry Tools | AIServices endpoint | `<ai-services-name>` |
| Minutes generation | Azure OpenAI in Microsoft Foundry Models | `gpt-5.4-mini`, `gpt-5.4` GlobalStandard capacity 100 each | Deployed |
| Search | Azure AI Search | Future phase | Not provisioned in current MVP |
| Monitoring | Application Insights + Log Analytics | Workspace-based | Deployed |

### Supporting Services

| Service | Purpose | Current state |
|---------|---------|---------------|
| Managed Identity | Service-to-service authentication | Function App system-assigned identity used |
| RBAC | Storage, Cosmos DB, Speech, OpenAI keyless access | Required roles assigned for dev MVP |
| Application Insights | Metrics, traces, dependency telemetry | Leak scan completed after live E2E |
| Log Analytics | Centralized telemetry storage | Deployed |

---

## 6. Provisioning Limit Checklist

Subscription-level template validation succeeded in `westus3`. Japan East and East US 2 were not used for this dev MVP because Microsoft.Web/serverFarms quota validation failed with Current Limit (Total VMs)=0.

| Resource Type | Number Deployed | Current Known Status | Notes |
|---------------|-----------------|----------------------|-------|
| Microsoft.Web/sites | 2 | Deployed | Function App + App Service frontend |
| Microsoft.Web/serverfarms | 2 | Deployed | Functions Premium EP1 + App Service plan |
| Microsoft.Storage/storageAccounts | 1 | Deployed | Blob + Durable storage |
| Microsoft.DocumentDB/databaseAccounts | 1 | Deployed | Cosmos DB for NoSQL |
| Microsoft.CognitiveServices/accounts | 1 | Deployed | AIServices `<ai-services-name>`, local auth disabled |
| Microsoft.Search/searchServices | 0 | Deferred | Azure AI Search remains future phase |
| Microsoft.Insights/components | 1 | Deployed | Application Insights |
| Microsoft.OperationalInsights/workspaces | 1 | Deployed | Log Analytics |
| Microsoft.ManagedIdentity/userAssignedIdentities | 0 | Not used | System-assigned identity used first |

Known quota/capacity facts:

- `westus3` subscription validation passed for the current Bicep template.
- App Service and Functions Premium EP1 template validation passed in West US 3.
- `gpt-5.4-mini` and `gpt-5.4` are deployed as GlobalStandard capacity 100 each. Capacity was increased after live smoke tests hit 429 during final merge.
- AI Search is intentionally not provisioned for the current MVP.

---

## 7. Execution Checklist

### Phase 1: Planning
- [x] Analyze workspace
- [x] Gather requirements
- [x] Confirm subscription and location
- [x] Scan codebase
- [x] Select recipe
- [x] Plan architecture
- [x] Complete deployment quota validation before azure-validate

### Phase 2: Execution
- [x] Research Azure Functions/App Service composition rules before final IaC
- [x] Generate bootstrap application files
- [x] Generate Azure Developer CLI configuration
- [x] Generate infrastructure
- [x] Deploy dev MVP

### Phase 3: Validation
- [x] Invoke azure-validate workflow
- [x] All validation checks pass
- [x] Backend and frontend build verification pass
- [x] Live API smoke pass
- [x] Live E2E smoke pass
- [x] Application Insights leak scan pass

### Phase 4: Production Hardening
- [ ] Enforce Microsoft Entra ID / Easy Auth for frontend/backend
- [ ] Disable demo auth outside local/dev-only scenarios
- [ ] Add user/tenant authorization tests
- [ ] Add stable representative short meeting-audio regression fixture
- [ ] Define performance regression thresholds for chunk fan-out, retry/backoff, and polling

---

## 8. Validation Proof

| Check | Command Run | Result | Timestamp |
|-------|-------------|--------|-----------|
| Bicep build | `az bicep build --file infra\main.bicep` | Passed | 2026-06-01 |
| Subscription validation | `az deployment sub validate --location japaneast --template-file infra\main.bicep --parameters environmentName=dev location=japaneast principalId=<signed-in-user>` | Blocked: Microsoft.Web/serverFarms quota in Japan East has Current Limit (Total VMs)=0; not used | 2026-06-01 |
| Subscription validation | `az deployment sub validate --location westus3 --template-file infra\main.bicep --parameters environmentName=dev location=westus3 principalId=<signed-in-user>` | Passed | 2026-06-01 |
| AZD installation | `azd version` | Passed: azd 1.25.4 | 2026-06-01 |
| AZD authentication | `azd auth login --check-status` | Passed: logged in | 2026-06-01 |
| Azure context | `az account show`; `azd env get-values` | Passed: subscription `<subscription-id>`, location `westus3` | 2026-06-01 |
| What-if preview | `az deployment sub what-if --location westus3 --template-file infra\main.bicep --parameters environmentName=dev location=westus3 principalId=<signed-in-user> --no-pretty-print` | Passed | 2026-06-01 |
| AZD provision preview | `azd provision --preview --no-prompt` | Passed; preview generated, no Azure resources changed | 2026-06-01 |
| Backend build verification | `uv run pytest --quiet`; `uv run ruff check . --quiet`; `uv run mypy .`; `uv run python ..\scripts\validate_specs.py` | Passed: 37 tests, lint/type/schema checks succeeded | 2026-06-01 |
| Frontend build verification | `npm run typecheck`; `npm test`; `npm run build` | Passed: 6 tests, typecheck/build succeeded | 2026-06-01 |
| Package validation | `azd package --no-prompt` | Passed; backend and frontend packages created | 2026-06-01 |
| Policy validation | `az policy assignment list --scope /subscriptions/<subscription-id>` | Passed with no blocking app-specific policy conflicts observed | 2026-06-01 |
| Live API smoke | frontend HTTP 200, backend health HTTP 200, job APIs | Passed | 2026-06-01 |
| Live E2E smoke | Short Japanese TTS WAV upload | Reached `DONE`; transcript/minutes retrieval worked | 2026-06-01 |
| Live E2E smoke | 55-minute m4a upload with preprocessing | Reached `DONE`; transcript/minutes retrieval worked; preprocessed FLAC stored | 2026-06-02 |
| Telemetry leak scan | Application Insights scan after live E2E | No SAS/query/audio/upload URLs/API keys/access tokens/client secrets/Bearer tokens found; Azure SDK Authorization traces redacted | 2026-06-01 |

---

## 9. Role Assignment Verification

- Status: Verified for dev MVP.
- Identities checked: Function App system-assigned managed identity, signed-in developer principal for Durable Task Scheduler local/admin access.
- Roles confirmed:
  - Function App -> Storage account: Storage Blob Data Owner.
  - Function App -> Storage account: Storage Blob Delegator.
  - Function App -> Storage queues/tables: Queue Data Contributor / Table Data Contributor.
  - Function App -> Durable Task Scheduler: Durable Task Data Contributor.
  - Signed-in developer principal -> Durable Task Scheduler: Durable Task Data Contributor.
  - Function App -> Cosmos DB account: Cosmos DB Built-in Data Contributor data-plane role assignment.
  - Function App -> AIServices `<ai-services-name>`: Cognitive Services OpenAI User.
  - Function App -> AIServices `<ai-services-name>`: Cognitive Services Speech User.

---

## 10. Deployment Result

- Resource provisioning: Succeeded.
- Frontend deployment: Succeeded.
- Backend deployment package upload: Succeeded.
- Backend runtime verification: Succeeded on Functions Premium EP1 with Python 3.13.

Endpoint status:

- Frontend: `https://<web-app-name>.azurewebsites.net/` returned HTTP 200.
- Backend health: `https://<function-app-name>.azurewebsites.net/api/health` returned HTTP 200.
- Backend API smoke: `POST /api/jobs` returned HTTP 201, `GET /api/jobs/{jobId}` returned HTTP 200, and `POST /api/jobs/{jobId}/upload-complete` returned HTTP 202.
- Result retrieval APIs: `GET /api/jobs/{jobId}/transcript` and `GET /api/jobs/{jobId}/minutes` are implemented, deployed, indexed, and verified from the live environment.
- Microsoft Foundry / AIServices resource: `<ai-services-name>` was created in `<resource-group>` / `westus3` with local auth disabled.
- Model deployments: `gpt-5.4-mini` and `gpt-5.4` are `GlobalStandard` deployments with capacity 100 each.
- Backend AI app settings: `AZURE_SPEECH_ENDPOINT`, `AZURE_OPENAI_BASE_URL`, `AZURE_OPENAI_DEPLOYMENT_CHUNK_SUMMARY`, and `AZURE_OPENAI_DEPLOYMENT_FINAL_MERGE` are populated from the provisioned AIServices resource/deployments.
- TTS end-to-end smoke: short Japanese speech WAV upload reached `DONE`; transcript and minutes retrieval APIs returned valid artifacts. Durable fan-out wrote chunk and chunk-summary artifacts under deterministic Blob paths.
- m4a end-to-end smoke: a 55-minute m4a file reached `DONE` after Backend preprocessing to 16kHz mono FLAC. Transcript and minutes retrieval APIs returned artifacts.
- `normalized-transcript.schema.json` and `minutes.schema.json` validation passed.

Important deployment notes:

- Flex Consumption was abandoned for this MVP deployment after repeated zero-function indexing with Python 3.13 packages.
- The backend runs on Functions Premium EP1 as `${resourcePrefix}-funcp`.
- Azure deployment package uses v1 `function.json` wrappers for stable Python 3.13 indexing in this environment; `function_app.py` remains for local tests and is excluded from deployment by `.funcignore`.
- `azure.yaml` backend package hooks temporarily copy root `specs/` into `backend/specs` so schema files are included in AZD-generated packages, then remove the temporary copy after packaging.
- `azure-functions` is pinned to `1.24.0` for worker compatibility.
- Function App host storage uses identity-based `AzureWebJobsStorage__accountName` + `AzureWebJobsStorage__credential=managedidentity`.
- Storage account data plane is intentionally public for the dev MVP because browser direct upload and Fast Transcription `audioUrl` require public endpoint reachability. Shared key access and blob anonymous public access remain disabled; access is by User Delegation SAS.
- m4a preprocessing runs inside `CreateReadSasActivity` using `imageio-ffmpeg` and writes `preprocessed/{tenantId}/{jobId}/input.flac`.
- Durable Orchestrator/Activity functions are registered with v1 `function.json` wrappers. Current E2E path performs real Fast Transcription, transcript normalization, Durable `task_all` chunk-summary fan-out, GPT-5.4 final merge, Markdown rendering, and Cosmos status updates.
- Application Insights leak scan after the latest live E2E found no SAS query strings, upload/audio URLs, API keys, access tokens, client secrets, or bearer tokens in request/trace/exception telemetry. Azure SDK `Authorization` traces were redacted.

---

## 11. Current Dev Auth Mode and Production Blocker

Current dev auth mode: `MEETING_MINUTES_AUTH_MODE=demo` is explicitly enabled for the dev MVP. Azure no longer trusts `x-dev-tenant-id` / `x-dev-user-id`; unauthenticated UI requests resolve to the fixed demo tenant/user until Entra ID integration is added.

This is **not production auth**. The current public endpoints must not be used for production or real/broader data until:

1. Microsoft Entra ID / Easy Auth is enforced for frontend/backend.
2. `MEETING_MINUTES_AUTH_MODE=demo` is disabled outside local/dev-only scenarios.
3. tenant/user authorization is based on validated token claims.
4. other-user and cross-tenant job access tests pass.
5. anonymous direct API calls cannot execute business APIs.

---

## 12. Next Steps

1. Enable Microsoft Entra ID / Easy Auth enforcement for public frontend/backend access and replace the dev MVP demo auth mode.
2. Add stable representative short meeting-audio regression fixture and expected quality checks.
3. Add/automate security regression scans for Application Insights secret/SAS leakage.
4. Define performance thresholds for `task_all` chunk fan-out, Azure OpenAI 429 retry/backoff, UI polling backoff, and total processing time.
5. Add recurring 55-80 minute m4a/WAV E2E regression and record quality, latency, token usage, and cost.

---

## 13. GitHub Actions CI/CD設計ノート

このリポジトリにはまだ `.github/workflows/` がない。現段階ではworkflow YAMLを追加せず、次のGitHub Actions設計を採用する。

### 13.1 Workflow構成

| ワークフロー | トリガー | Environment | 概要 |
|----------|---------|-------------|------|
| PR CI | `pull_request` | なし | backend / frontend / infra / securityの静的検証。Azure OIDC loginはしない |
| dev deploy | CI成功後の `main` push | `dev` | OIDCでAzureへログインし、`azd provision` と `azd deploy` を実行 |
| prod deploy | `workflow_dispatch` | `prod` | required reviewers、branch/tag protection、prod assertion通過後だけ実行 |

PR CI concurrencyはPR単位で `cancel-in-progress: true`。deploy/provision concurrencyはenvironment単位で `cancel-in-progress: false` とし、同一環境への同時provision/deployを防ぐ。

### 13.2 CIコマンド

GitHub runnerは既存コマンド表記に合わせて `windows-latest` / PowerShellを既定にする。

Backend:

```powershell
cd backend
uv sync --frozen
uv run ruff check .
uv run mypy .
uv run pytest --quiet
uv run python ..\scripts\validate_specs.py
```

Frontend:

```powershell
cd frontend
npm ci
npm run typecheck
npm test
npm run build
```

Infra:

```powershell
az bicep build --file infra\main.bicep
```

OIDC変数を使えるtrusted branchでは、PRまたはpre-deployの追加確認として `azd provision --preview --no-prompt`、または `az deployment sub what-if/validate` を実行できる。

ランタイム/cache:

- Pythonは3.13 exactly。`backend\pyproject.toml` も `>=3.13,<3.14` のため、CIで3.14へ上げない。
- Nodeは20。
- uv cacheは `backend\uv.lock` をkeyにする。
- npm cacheは `frontend\package-lock.json` をkeyにする。

### 13.3 AZD deploy手順

dev/prodのdeploy jobはCI成功後に実行する。

1. GitHub Environment `dev` または `prod` を指定する。
2. permissionsはdeploy jobだけ `contents: read` と `id-token: write`。
3. `azure/login` をOIDCで実行する。client secret、publish profile、`AZURE_CREDENTIALS` は使わない。
4. `AZURE_SUBSCRIPTION_ID`、`AZURE_LOCATION`、`AZURE_ENV_NAME`、`AZURE_PRINCIPAL_ID` を設定する。`AZURE_PRINCIPAL_ID` はservice principal object IDであり、application/client IDではない。
5. 次を順に実行する。

```powershell
azd provision --no-prompt
azd deploy backend
azd deploy frontend
```

`azure.yaml` のbackend `prepackage` hookは、root `specs/` をbackend packageへコピーしてからpackage後に削除する。Functions package内でschema validationが動くため、このhookをCI/CDでも維持する。AZD deploy runnerではPythonをPATHに置く。

### 13.4 OIDCとRBAC

GitHub Environmentごとのfederated credential subject:

- dev: `repo:<ORG>/<REPO>:environment:dev`
- prod: `repo:<ORG>/<REPO>:environment:prod`

現行Bicepはsubscription-scopeでrole assignmentsも作成する。継続deploy identityには次のどちらかを選ぶ。

| 選択肢 | 用途 | RBAC |
|--------|----------|------|
| A. dev暫定 | dev MVPで現行IaCをそのまま回す | subscription-scope Contributor + User Access Administrator / RBAC Administrator / Owner相当 |
| B. 本番推奨 | 本番向けにbootstrapとrecurring deployを分離 | bootstrap identityがrole assignmentを作り、recurring deploy identityは最小権限へ縮小 |

現行Bicepに `principalType: 'User'` 前提の補助role assignmentが残る場合、CI/CDでservice principal object IDを渡す前にIaCを修正するか、bootstrap手順へ分離する。

### 13.5 本番ブロッカーとゲート

prod deployは次を満たすまで実行しない。

- `MEETING_MINUTES_AUTH_MODE != demo`
- Frontend/BackendでMicrosoft Entra ID / Easy Authが有効。
- anonymous direct API callが業務APIを実行できない。
- 他ユーザー/別tenant jobアクセス拒否テストが成功。
- secret scanning/gitleaks、CodeQL、`pip-audit`、`npm audit`、Bicep buildが成功。

現在のdev MVPは `MEETING_MINUTES_AUTH_MODE=demo` であるため、本番deployはblocked。
