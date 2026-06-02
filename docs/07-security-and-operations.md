# 07. セキュリティ・運用設計

確認日: 2026-06-01

## 1. セキュリティ原則

- 顧客音声、transcript、議事録は機密データとして扱う。
- ストレージキーやAPIキーをコード、ログ、フロントエンドに出さない。
- 認証は Microsoft Entra ID と managed identity を優先する。
- SASは必要最小限の権限と短い有効期限にする。
- 本文データを Application Insights に出さない。
- dev MVPの利便性設定を本番認証と混同しない。

## 2. 認証・認可

### 2.1 ユーザー認証

- Web UI/APIは Microsoft Entra ID 認証を前提にする。
- tenantId と userId を token claims から取得する。
- APIリクエストの tenantId をクライアント入力だけに依存しない。
- job取得、transcript取得、minutes取得、speaker mapping更新は、同一tenantかつ権限を持つuserだけに許可する。

### 2.2 dev MVPの暫定認証と本番化ブロッカー

2026-06-01時点のdev MVPでは、UIからの実E2E確認を優先するため `MEETING_MINUTES_AUTH_MODE=demo` を明示設定し、固定の `demo-tenant` / `demo-user` で動かす。Azure環境では `x-dev-tenant-id` / `x-dev-user-id` を信用しない。

ただし、HTTP trigger + demo認証は本番・実データ・広範な共有利用には安全ではない。代表音声や実データを扱う前に、次を必須条件として満たす。

1. Frontend/App Service と Backend/API で Microsoft Entra ID / Easy Auth を強制する。
2. anonymous HTTP trigger に直接到達しても、業務APIがdemo userとして処理されないようにする。
3. token claims 由来の tenantId / userId を job所有者検証に使う。
4. 他ユーザーjobId、別tenant jobId、無効token、期限切れtokenの拒否テストを追加する。
5. `MEETING_MINUTES_AUTH_MODE=demo` を本番slot/環境で設定できない運用ガードを入れる。

### 2.3 Azureリソース間認証

- API Functions から Blob/Cosmos/Speech/OpenAI へは managed identity を優先する。
- Storage へのSAS発行は User Delegation SAS を使う。
- Speech/OpenAIも可能な範囲で keyless authentication を使う。
- Azure OpenAI in Microsoft Foundry Models は v1 API を使い、`api-version`付きの古い呼び出しを新規追加しない。

### 2.4 RBAC

| 対象ID | 対象リソース | 想定ロール | 用途 | dev MVP状態 |
|---|---|---|---|---|
| Azure Functions managed identity | Storage account / container | Storage Blob Data Owner / Data Contributor | Blobの存在確認、読み書き、成果物保存 | 付与済み |
| Azure Functions managed identity | Storage account | Storage Blob Delegator | User Delegation SAS発行。storage accountスコープで付与し、containerスコープでは付与しない | 付与済み |
| Azure Functions managed identity | Storage queues/tables | Queue Data Contributor / Table Data Contributor | identity-based host storage / Durable関連 | 付与済み |
| Azure Functions managed identity | Durable Task Scheduler | Durable Task Data Contributor | orchestration実行 | 付与済み |
| Azure Functions managed identity | Azure Cosmos DB for NoSQL | Cosmos DB Built-in Data Contributor | job状態、speaker mapping、action items保存。Cosmos DB data-plane RBACとして付与する | 付与済み |
| Azure Functions managed identity | Azure Speech in Foundry Tools | Cognitive Services Speech User | Fast Transcriptionのkeyless呼び出し | 付与済み |
| Azure Functions managed identity | Azure OpenAI in Microsoft Foundry Models | Cognitive Services OpenAI User | v1 APIのkeyless呼び出し | 付与済み |
| 利用ユーザー | API | アプリ側ロール/Entra ID認可 | 自分のtenantId/userIdに属するjobだけを操作 | 本番化前に必須 |

Storage account key はSAS発行にもアプリ設定にも使わない。keyless認証が未対応または制約で使えない場合は、例外理由、期限、ローテーション方法をADRに残す。

## 3. SAS設計

### アップロードSAS

| 項目 | 設計 |
|---|---|
| 種類 | User Delegation SAS |
| 権限 | create/write のみ。必要に応じて read なし |
| 対象 | jobId専用blob path |
| TTL | 10〜30分 |
| プロトコル | HTTPSのみ |
| IP制限 | 顧客環境に応じて検討 |

### Speech用読み取りSAS

| 項目 | 設計 |
|---|---|
| 種類 | User Delegation SAS |
| 権限 | readのみ |
| 対象 | raw-audio blobのみ |
| TTL | 初期値90分。Speechサービスのfetchとretryが完了するまで有効にする |
| 用途 | Fast Transcription `audioUrl` |

SAS URL全文はAPIレスポンスで必要な場面を除き、ログ、例外、Application Insights dependency name、custom dimensionsへ出さない。

## 4. ネットワーク

初期PoCでは public endpoint + Entra ID / SAS でよい。dev MVPのdemo認証モードは公開本番向けではない。現在のFast Transcription経路は `audioUrl` を使うため、Storage Blobのデータ面は公開エンドポイントで到達可能である必要がある。Storageは `publicNetworkAccess=Enabled` / `defaultAction=Allow` で、データ面は公衆網から到達可能である。共有キーとBlob匿名公開は無効化し、User Delegation SASと短いTTLで保護する。`bypass=AzureServices` は補助設定であり、Azureサービスだけに限定する制御ではない。厳格な閉域要件がある場合は、Fast Transcription `audioUrl` 経路のままではなく、Batch TranscriptionなどStorage private endpointとmanaged identityアクセスに対応できる別経路を設計する。

Storage public endpoint は過去にIaC外で `Disabled` へドリフトし、User Delegation SAS発行が403になって `POST /api/jobs` が500になった。Bicepでは `publicNetworkAccess=Enabled` と `networkAcls.defaultAction=Allow` を明示する。Azure Policyは2026-06-02時点でauditのみ確認済みだが、Policy/手動変更による再ドリフトを監視する。

### 4.1 m4a前処理

m4aはFast Transcription直渡しで `InvalidAudioFormat` になるケースがあるため、Backend Activity内で16kHz mono FLACへ変換してから `audioUrl` を渡す。変換は `imageio-ffmpeg` が同梱するffmpegバイナリをsubprocess実行する。ffmpeg stderr、ローカル一時パス、SAS URL、音声内容はエラーdetailsやログへ出さない。

### 4.2 CORS

2026-06-02時点のlive確認では、Function App と Storage Blob のCORS設定をIaCで明示し、frontend App Service originだけを既定許可している。ブラウザからの現行dev MVPを安全に動かすため、IaCでは次を維持する。

- 許可originはデプロイ済みApp Service frontendの `https://{webAppName}.azurewebsites.net` を既定にする。
- wildcard originは使わない。ローカルViteからAzure API/Storageへ接続する検証が必要な場合だけ、`additionalCorsAllowedOrigins` に `http://localhost:5173` などの完全一致originをdev用途で追加する。
- Function App CORSは `supportCredentials: false` とし、demo認証の代替にしない。
- Storage Blob CORSは直接アップロードに必要な `PUT` とpreflight用 `OPTIONS`、`x-ms-blob-type` / `content-type` などの最小ヘッダーを許可する。
- Storage Blob CORSの `maxAgeInSeconds` は600秒にし、preflightの繰り返しを減らす。これは性能改善であり、認証・認可の代替ではない。

注意:

- `audioUrl` 方式では Speech サービスがBlob URLへ到達できる必要がある。
- 完全閉域にする場合は、WorkerがBlobから音声を読み、Speech APIへ送る代替経路が必要になる。ただし inline `audio` 方式には別のサイズ制限があり、大きい音声では使いにくい。二重転送にもなるため、初期PoCの低レイテンシ経路にはしない。

## 5. データ保護

### 保存時暗号化

Azure Storage、Cosmos DB、Application Insights の標準暗号化を使う。顧客要件に応じて customer-managed key を検討する。

### データ削除

- raw audio は既定30日で削除する。
- transcript と minutes は業務要件に合わせる。
- ユーザー削除要求がある場合、jobId単位で関連BlobとCosmos DBレコードを削除する。

## 6. ログ設計

ログに出してよいもの:

- jobId
- tenantId
- userIdのハッシュ値
- fileSizeBytes
- audioDurationSeconds
- status
- retryCount
- elapsedMilliseconds
- modelDeployment
- tokenUsage
- error code

ログに出してはいけないもの:

- 音声本文
- transcript全文
- 議事録全文
- SAS URL全文
- アクセストークン
- Storage account key
- API key
- client secret
- Authorization header / Bearer token

## 7. Application Insights

### custom metrics

| メトリック | 単位 |
|---|---|
| `meeting.upload.seconds` | seconds |
| `meeting.transcription.seconds` | seconds |
| `meeting.normalization.seconds` | seconds |
| `meeting.chunk_summary.seconds` | seconds |
| `meeting.final_merge.seconds` | seconds |
| `meeting.total.seconds` | seconds |
| `meeting.speech.retry_count` | count |
| `meeting.openai.retry_count` | count |
| `meeting.openai.prompt_tokens` | tokens |
| `meeting.openai.completion_tokens` | tokens |
| `meeting.minutes.schema_validation_failures` | count |
| `meeting.activity.duration.seconds` | seconds |

### custom dimensions

- jobId
- tenantId
- status
- activityName
- speechRegion
- openaiDeploymentName
- errorCode

### Activity duration logs

2026-06-02時点では、各Durable Functions Activity wrapperで処理時間を計測し、`meeting.activity.duration.seconds` をApplication Insightsログへ出す。ログに出すdimensionは `tenantId`, `jobId`, `activityName`, `outcome`, `chunkIndex`, `errorType`, `errorCode` のallowlistに限定し、payload全文、SAS URL、transcript、minutes、音声本文は出さない。

E2Eが遅い場合は、まず次のKQLでActivity別の所要時間を確認する。

```kusto
traces
| where timestamp > ago(24h)
| where message has "meeting.activity.duration.seconds"
| extend payload = parse_json(message)
| extend dims = payload.dimensions
| project
    timestamp,
    jobId = tostring(dims.jobId),
    activityName = tostring(dims.activityName),
    outcome = tostring(dims.outcome),
    chunkIndex = tostring(dims.chunkIndex),
    durationSeconds = todouble(payload.value)
| summarize
    count(),
    avgDurationSeconds = avg(durationSeconds),
    p95DurationSeconds = percentile(durationSeconds, 95),
    maxDurationSeconds = max(durationSeconds)
  by activityName, outcome
| order by maxDurationSeconds desc
```

`GenerateChunkSummaryActivity` はOrchestratorで並列実行されるため、Activity durationの単純合計はE2E壁時計時間と一致しない。E2E短縮判断では、STTなど単一Activityの最大時間、chunk summaryのbatch内最大時間、OpenAI/Speechの429/5xx再試行有無を合わせて見る。

### 現在の確認実績

最新のlive E2E後にApplication Insightsをスキャンし、SAS query strings、upload/audio URLs、API keys、access tokens、client secrets、Bearer tokensは検出されなかった。Azure SDK `Authorization` traces はredact済みだった。

このスキャンは本番安全性の証明ではなく、回帰テストとして継続する。新しいSDK、middleware、exception handlingを追加した場合は再スキャンする。

## 8. アラート

| 条件 | 重要度 | 対応 |
|---|---:|---|
| FAILED率が15分で10%超 | 高 | Speech/OpenAI/Storage障害を確認 |
| Speech 429が増加 | 中 | 並列度を下げる、クォータ確認 |
| OpenAI 429が増加 | 中 | chunk並列度を下げる、TPM確認、deployment capacity確認 |
| 平均total secondsが急増 | 中 | ボトルネックを分解確認 |
| Blob SAS発行失敗 | 高 | managed identity/RBAC確認 |
| demo認証設定が本番環境で検出 | 高 | 即時無効化し、公開経路を停止 |
| 機密ログ検出 | 高 | 該当release停止、ログ削除/保持ポリシー確認、redaction修正 |

## 9. クォータ管理

### Speech

- Fast Transcription はリソースあたり最大600 requests/min。
- 音声入力は500MB未満、5時間未満。diarization有効時は2時間未満。
- ただし初期UX上限は300MBにする。

### Azure OpenAI in Microsoft Foundry Models

- TPM/RPMはサブスクリプション、リージョン、モデルまたはデプロイ種別ごとに定義される。
- dev MVPでは `gpt-5.4-mini` と `gpt-5.4` をGlobalStandard capacity 100に増強済み。
- chunk summary の並列度は設定値で制御する。
- 429が増えたら、並列度を下げる、capacity/quotaを確認する、指数バックオフを確認する。

## 10. 障害時の対応

### Speech API失敗

1. エラーコードを正規化する。
2. リトライ対象なら指数バックオフで再試行する。
3. 失敗した場合は `FAILED` にし、ユーザー向けメッセージを保存する。
4. 管理者は `retry` API で再実行できる。

### OpenAI失敗

1. 429/5xxは再試行する。
2. JSON Schema validation失敗は修復プロンプトを1回試す。
3. それでも失敗したら `MINUTES_GENERATION_FAILED` にする。
4. 429が継続する場合はcapacity、TPM/RPM、chunk並列度を見直す。

### Blob読み取り失敗

1. SAS期限切れなら再発行する。
2. Blobがない場合は `AUDIO_BLOB_NOT_FOUND` にする。

## 11. コスト管理

- raw audio の保持期間を短くする。
- transcript と minutes は圧縮を検討する。
- chunk summary のプロンプトを短く保つ。
- MarkdownはLLMではなくコードで生成する。
- モデルは品質・レイテンシ・コストを実測で選ぶ。
- UIポーリングをbackoffし、不要なAPI呼び出しを避ける。

## 12. 責任あるAI観点

- diarization は speaker ID を割り当てる機能であり、個人識別ではない。
- UIには「話者名は自動識別ではありません。必要に応じて手動で紐付けてください」と表示する。
- 議事録は自動生成であり、共有前に確認する導線を用意する。

## 13. GitHub Actions CI/CDセキュリティ

### 13.1 基本方針

- GitHub ActionsではOIDC federationのみを使う。
- client secret、publish profile、`AZURE_CREDENTIALS`、API key、Storage account key、SAS URL全文をGitHub Secretsやログに保存しない。
- OIDC subjectはGitHub Environment単位に固定する。
  - dev: `repo:<ORG>/<REPO>:environment:dev`
  - prod: `repo:<ORG>/<REPO>:environment:prod`
- PR CI jobのpermissionsは原則 `contents: read` のみにする。AzureへログインしないPR、特にfork PRには `id-token: write` を付与しない。
- deploy/provision jobだけ `contents: read` と `id-token: write` を付与する。CodeQL uploadを使うjobだけ必要に応じて `security-events: write` を付与する。

### 13.2 GitHub Environments

| Environment | 用途 | 必須ゲート |
|---|---|---|
| `dev` | 手動 `workflow_dispatch` による検証・デプロイ | CI成功、OIDC subject固定、環境単位concurrency、`dry_run=true` 既定 |
| `prod` | 本番候補の手動デプロイ | required reviewers、保護ブランチ/タグ、手動 `workflow_dispatch`、demo認証無効化確認 |

deploy/provisionは環境ごとのconcurrency groupを使い、`cancel-in-progress: false` にする。途中でprovisionやrole assignmentを中断して環境を半端な状態にしない。現行dev workflowは自動push deployではなく手動実行のみ。

### 13.3 Azure OIDC変数

`azure/login` には、GitHub EnvironmentのVariablesまたはSecretsとして次を渡す。これらはclient secretではない。

| 変数 | 値 | 注意 |
|---|---|---|
| `AZURE_CLIENT_ID` | federated credentialを設定したアプリケーションのclient ID | object IDではない |
| `AZURE_TENANT_ID` | tenant ID |  |
| `AZURE_SUBSCRIPTION_ID` | 対象subscription ID |  |
| `AZURE_LOCATION` | 例: `westus3` | `azd`/Bicepに渡す |
| `AZURE_ENV_NAME` | `dev` または `prod` | GitHub Environment名と揃える |
| `AZURE_PRINCIPAL_ID` | deploy service principalのobject ID | client IDではない。Bicepのrole assignmentや`azd provision`へ渡す |
| `AZURE_DEMO_ACCESS_KEY` | 顧客デモ用の共有アクセスキー（合言葉） | 十分長いランダム値。コミット禁止。未設定だと Azure 上で fail-closed |
| `AZURE_PROXY_SECRET` | フロントエンド→Functions 間の内部シークレット | `AZURE_DEMO_ACCESS_KEY` と別の値。ブラウザには出さない。コミット禁止 |

顧客デモのアクセスゲートは、フロントエンド（App Service / Express）が合言葉を検証して署名付き httpOnly Cookie でセッションを張り、`/api/*` を Function App へリバースプロキシして `MEETING_MINUTES_PROXY_SECRET` をサーバー側で注入する方式。Function App は `x-proxy-secret` を検証し、URL 直叩きを拒否する。これは個人認証ではなくデモ用簡易ゲート。詳細は `SECURITY.md`。

現行Bicepにユーザーprincipal前提の補助role assignmentが残る場合は、CI/CD化前にservice principal object IDを扱えるようにするか、該当role assignmentをbootstrap手順へ分離する。

### 13.4 RBAC設計

現行Bicepはsubscription-scopeで、provision時にrole assignmentも作成する。そのため、同じテンプレートを継続的に `azd provision` するdeploy identityにはrole assignment書き込み権限が必要になる。

| 選択肢 | 想定 | deploy identity権限 |
|---|---|---|
| A. dev向け暫定運用 | MVP/devで速度を優先し、現行IaCを大きく分割しない | subscription-scope Contributor + User Access Administrator / RBAC Administrator / Owner相当 |
| B. 本番推奨 | 一度きりのbootstrap identityがrole assignmentを作成し、通常deployからRBAC作成を外すIaCへ分離する | recurring deploy identityは対象resource group/App Service/Functions/Storage等に必要な最小権限 |

本番ではBを目標にする。Aをprodへ持ち込む場合は、期限付き例外としてリスク、期限、監査方法を記録する。

### 13.5 セキュリティゲート

CI/CDには次を含める。

- secret scanningまたはgitleaks。
- CodeQL。
- backend依存監査: `pip-audit` など。uv環境へ追加する場合はCI専用手順として扱い、依存定義に追加するかは別途判断する。
- frontend依存監査: `npm audit`。
- Bicep build。必要に応じてBicep lint、PSRule for Azureを追加する。
- prod deploy前のassertion:
  - `MEETING_MINUTES_AUTH_MODE != demo`
  - Frontend/BackendでMicrosoft Entra ID / Easy Authが有効。
  - anonymous direct API callが業務APIを実行できない。

現在のdev MVPは `MEETING_MINUTES_AUTH_MODE=demo` のため、prod deployは明示的にブロックする。
