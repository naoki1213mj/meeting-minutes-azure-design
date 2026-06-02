# 13. Public-safe deployment plan and runbook

> **Status:** Dev MVP / production hardening pending
>
> この文書は公開リポジトリ向けの runbook です。実在する subscription ID、tenant ID、resource group、endpoint URL、SAS URL、job ID、ローカル音声ファイル名、顧客名は記載しません。環境固有の証跡は private release notes または安全な運用記録に分離してください。

Last updated: 2026-06-02

## 1. 目的

Minutes Studio を Azure 上に dev MVP として構築・検証するための公開安全な手順を定義します。production deployment は、Microsoft Entra ID / Easy Auth とユーザー単位認可が完了するまで blocked です。

## 2. 前提

| 項目 | 前提 |
|---|---|
| アプリ分類 | Development / MVP |
| 既定ランタイム | Python 3.13、Node.js 20 |
| IaC | Bicep + Azure Developer CLI |
| Backend | Azure Functions Premium + Durable Functions |
| Frontend | React + Vite + Azure App Service |
| Storage | Azure Blob Storage |
| Metadata | Azure Cosmos DB for NoSQL |
| AI | Azure Speech in Foundry Tools、Azure OpenAI in Microsoft Foundry Models |
| Observability | Azure Monitor Application Insights |
| Production readiness | Entra ID / Easy Auth と user authorization 完了まで未対応 |

この runbook の placeholder:

| Placeholder | 意味 |
|---|---|
| `<subscription-id>` | Azure subscription ID |
| `<tenant-id>` | Microsoft Entra tenant ID |
| `<resource-group>` | Resource group name |
| `<azure-region>` | Deployment region |
| `<principal-object-id>` | RBAC 付与対象の object ID |
| `<web-app-name>` | Frontend App Service name |
| `<function-app-name>` | Function App name |
| `<ai-services-name>` | AIServices resource name |
| `<ORG>/<REPO>` | GitHub organization / repository |

## 3. Architecture snapshot

```text
Browser
  -> Azure Functions API
  -> User Delegation SAS
  -> Azure Blob Storage direct upload
  -> Durable Functions orchestration
  -> Azure Speech in Foundry Tools Fast Transcription + diarization
  -> normalized transcript
  -> Azure OpenAI in Microsoft Foundry Models v1 API
  -> minutes JSON / Markdown
  -> Blob Storage + Cosmos DB + Application Insights
```

設計の本線:

- 文字起こしは全体音声に対して 1 回だけ実行する。
- diarization を有効化し、`channels` は指定しない。
- 議事録生成は transcript 全文を使う direct generation を本線にする。
- chunk summary 方式は direct generation が出力切れ等で失敗した場合の自動 fallback として残す。
- 本番経路では Fast Transcription に `audioUrl` を渡す。
- inline `audio` は小さい開発・検証に限定する。
- Azure OpenAI in Microsoft Foundry Models は v1 API を使い、dated `api-version` を新規追加しない。

## 4. Local validation

Backend:

```powershell
cd backend
uv sync
uv run ruff check .
uv run mypy .
uv run pytest --quiet
uv run python ..\scripts\validate_specs.py
```

Frontend:

```powershell
cd frontend
npm install
npm run typecheck
npm test
npm run build
```

Infra:

```powershell
az bicep build --file infra\main.bicep
```

Schema-only check:

```powershell
python -m json.tool specs\minutes.schema.json > $null
python -m json.tool specs\minutes.structured-output.schema.json > $null
python -m json.tool specs\chunk-summary.structured-output.schema.json > $null
python -m json.tool specs\normalized-transcript.schema.json > $null
```

## 5. Azure Developer CLI environment

```powershell
azd env new dev --no-prompt
azd env set AZURE_SUBSCRIPTION_ID "<subscription-id>"
azd env set AZURE_LOCATION "<azure-region>"
azd env set AZURE_PRINCIPAL_ID "<principal-object-id>"
# 顧客デモのアクセスゲート（互いに異なる強いランダム値を設定。未設定だと Azure 上で fail-closed）
azd env set AZURE_DEMO_ACCESS_KEY "<long-random-key>"
azd env set AZURE_PROXY_SECRET "<another-long-random-secret>"
```

`AZURE_DEMO_ACCESS_KEY` は顧客に伝える合言葉、`AZURE_PROXY_SECRET` はフロントエンド→Functions 間の内部シークレットです（別の値にし、ブラウザには出しません）。詳細は `SECURITY.md` の「顧客デモのアクセス制御」を参照してください。

公開ドキュメント、Issue、PR には `azd env get-values` の実出力を貼らないでください。

## 6. Provision and deploy

Preview / validation:

```powershell
azd provision --preview --no-prompt
```

Provision and deploy:

```powershell
azd provision --no-prompt
azd deploy backend
azd deploy frontend
```

運用メモ:

- `azure.yaml` の backend package hook は root `specs/` を package に含めるために必要です。
- Functions package には schema validation に必要な JSON Schema を含めます。
- Backend は Python 3.13 を前提にします。CI や runner で Python 3.14 へ上げる場合は ADR を更新してください。
- Storage Blob data plane は、browser direct upload と Fast Transcription `audioUrl` のため public endpoint 到達性が必要です。Blob 匿名公開と shared key access は無効化し、User Delegation SAS で保護します。
- Content Understanding の動画理解（実験）経路を使う場合は、`gpt-4.1-mini-cu` deployment、Content Understanding default model mapping、`minutes_video_ja` analyzer が必要です。BicepはdeploymentとFunction App設定を作成しますが、Content Understanding default mapping と analyzer 作成は現時点では手動/補助スクリプト手順として管理します。公開ログに endpoint、token、SAS URL、実動画名を貼らないでください。

## 7. Smoke test checklist

公開 runbook では実ジョブ ID や実 URL を記録しません。結果を共有する場合は、次のように placeholder と要約だけを使います。

| Check | Expected result |
|---|---|
| Frontend health | `<web-app-name>` が HTTP 200 を返す |
| Backend health | `<function-app-name>` の health API が HTTP 200 を返す |
| Job create | `POST /api/jobs` が `201 Created` を返す |
| Direct upload | Browser upload が完了する |
| Upload complete | `POST /api/jobs/{jobId}/upload-complete` が `202 Accepted` を返す |
| Workflow | Job status が terminal state へ進む |
| Transcript | schema validation 済み transcript を取得できる |
| Minutes | schema validation 済み minutes を取得できる |
| Telemetry | SAS/query/audio/upload URL、token、key、secret が telemetry に出ていない |

実行ログを残す場合は、音声本文、transcript、minutes、SAS URL、job ID、実 endpoint を redaction してください。

## 8. GitHub Actions design note

CI workflow は `.github/workflows/ci.yml` を参照します。README の badge も同じ workflow file path を使います。workflow 名や path を変更する場合は、README の badge も同時に更新してください。

推奨構成:

| Workflow | Trigger | Environment | Summary |
|---|---|---|---|
| PR CI | `pull_request` | none | backend / frontend / infra / security validation。Azure OIDC login は行わない |
| dev deploy | manual `workflow_dispatch` | `dev` | OIDC/RBACを検証する。既定は `dry_run=true` でAzureリソースを変更しない |
| prod deploy | manual `workflow_dispatch` | `prod` | demo auth解消とproduction gate完了まで常時blocked |

Permissions:

- CI job は最小権限にする。
- deploy job だけ `contents: read` と `id-token: write` を付与する。
- client secret、publish profile、`AZURE_CREDENTIALS`、API key、Storage key、SAS URL を GitHub Secrets に保存しない。

OIDC subject 例:

```text
repo:<ORG>/<REPO>:environment:dev
repo:<ORG>/<REPO>:environment:prod
```

## 9. RBAC guidance

継続 deploy identity は最小権限に寄せます。初回 bootstrap と通常 deploy を分けられる場合は、role assignment 作成権限を bootstrap 側に限定してください。

必要な観点:

- Function App managed identity から Blob Storage への data-plane access。
- Function App managed identity から Cosmos DB data-plane access。
- Function App managed identity から Azure Speech in Foundry Tools / Azure OpenAI in Microsoft Foundry Models への keyless access。
- Durable Functions / Durable Task Scheduler に必要な権限。
- 人間または CI principal が過剰な subscription-scope 権限を持ち続けないこと。

## 10. Production gate

Production deployment は次を満たすまで blocked です。

- `MEETING_MINUTES_AUTH_MODE=demo` が production で使われない。
- Frontend / Backend で Microsoft Entra ID / Easy Auth が強制される。
- token claims に基づく tenant/user authorization が実装される。
- anonymous direct API call が business API を実行できない。
- 他ユーザー / cross-tenant job access 拒否テストが成功する。
- secret scanning、dependency audit、Bicep build、backend/frontend tests が成功する。
- Application Insights などの telemetry に SAS、token、key、音声本文、transcript、minutes が出ていない。
- 代表音声で品質、処理時間、429 retry、コストを確認する。

## 11. Public-safety checklist

公開前に次を確認してください。

- [ ] 実在する Azure ID / resource name / endpoint URL が含まれていない。
- [ ] 実 job ID、実 SAS URL、実 upload URL、実 audio URL が含まれていない。
- [ ] ローカルの実音声ファイル名、顧客名、個人情報が含まれていない。
- [ ] README に broken placeholder badge がない。
- [ ] `SECURITY.md` の非公開報告経路が設定されている。
- [ ] docs と specs の本線に矛盾していない。
