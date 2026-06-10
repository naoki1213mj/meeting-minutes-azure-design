# 02. アーキテクチャ設計

確認日: 2026-06-01

## 1. 全体構成

```text
[React Web UI on Azure App Service]
  |
  | POST /api/jobs
  v
[Azure Functions API: Premium EP1 / Python 3.13]
  |
  | User Delegation SAS
  v
[Public Ingest Storage: raw-audio / preprocessed]
  ^
  |
  | direct upload from browser
  |
[React Web UI]
  |
  | POST /api/jobs/{jobId}/upload-complete
  v
[Durable Functions Orchestrator]
  |
  +--> ValidateJobInput Activity
  |
  +--> TranscribeAudio Activity
  |      -> Azure Speech in Foundry Tools
  |      -> Fast Transcription + diarization
  |
  +--> NormalizeTranscript Activity
  |
  +--> GenerateFinalMinutes Activity
  |      -> Azure OpenAI in Microsoft Foundry Models
  |      -> direct full-transcript generation
  |      -> chunk fallback only when needed
  |
  +--> RenderMarkdown / PersistOutputs Activities
  |
  v
[Storage]
  Public Ingest Storage
    - raw-audio/
    - preprocessed/
  Private Artifact Storage (mid-term)
    - transcript/raw/
    - transcript/normalized/
    - transcript/chunks/
    - minutes/json/
    - minutes/markdown/
    - visual-context/

[Cosmos DB]
  - jobs
  - speakerMappings
  - actionItems
  - auditEvents

[Application Insights]
  - traces
  - dependencies
  - custom metrics
```

## 2. Azureリソース

| リソース | 役割 | dev MVP状態 |
|---|---|---|
| Azure App Service | React Web UI配信 | デプロイ済み: `<web-app-name>` |
| Azure Functions Premium EP1 | APIとDurable Functions | デプロイ済み: `<function-app-name>` |
| Durable Functions / Durable Task Scheduler | 長時間ジョブの状態管理 | デプロイ済み。orchestrator/activity は v1 `function.json` wrappersで登録 |
| Ingest Blob Storage | raw upload、Speech/CUが取得する入力、標準経路の前処理済みFLAC保存 | dev MVPでは既存Storageを使用。public endpoint有効、共有キー/Blob匿名公開は無効 |
| Artifact Storage | raw transcript response、normalized transcript、chunk、minutes JSON/Markdown、visual contextなどの成果物保存 | 中期対策でPrivate Endpoint付きの別Storage accountへ分離 |
| Azure Cosmos DB for NoSQL | ジョブ状態・speaker mapping保存 | デプロイ済み |
| AIServices `<ai-services-name>` | Speech/OpenAI/CU統合のMicrosoft Foundry resource | デプロイ済み。local auth disabled、project management enabled |
| Microsoft Foundry project `minutes-studio` | new Foundry portalでのデモ/実験用project child resource | デプロイ済み。classic `Microsoft.MachineLearningServices/workspaces` hub/projectは使わない |
| Azure Speech in Foundry Tools | Fast Transcription + diarization | AIServices endpointを使用 |
| Azure OpenAI in Microsoft Foundry Models | 議事録生成 | `gpt-5.4-mini`, `gpt-5.4`、GlobalStandard capacity 100 each |
| Application Insights + Log Analytics | 監視・トレース | デプロイ済み。機密ログ漏えいスキャン実施済み |
| Azure Container Apps Jobs | 大型音声/動画前処理 | 未導入。現在のm4a/mp4前処理はFunctions内の `imageio-ffmpeg` で実施。より重い前処理はPhase 2候補 |
| Azure SignalR Service | 進捗push通知 | 未導入。Phase 2候補 |
| Azure AI Search | 過去議事録検索 | 未導入。Phase 3候補 |

### 2.1 現在のdevエンドポイント

- Frontend: `https://<web-app-name>.azurewebsites.net/`
- Backend health: `https://<function-app-name>.azurewebsites.net/api/health`
- Subscription: `<subscription-id>`
- Resource group: `<resource-group>`
- Region: `westus3`

### 2.2 アーキテクチャ図

- `docs/diagrams/azure-resource-architecture.drawio`: Azureサービスアイコン付きのリソース構成図。
- `docs/diagrams/azure-network-architecture.drawio`: public ingest と Private Endpoint / Private DNS の境界を示すネットワーク構成図。
- `docs/diagrams/azure-architecture.drawio`: 主要フローを簡潔に示す概要図。

### 2.3 中期ネットワークハードニング

中期対策では、Storageを public ingest と private artifact に分ける。

- public ingest Storage: ブラウザ直接アップロード、Speech/CUが取得する raw input、標準経路の前処理済みFLACを置く。
- private Artifact Storage: raw transcript response、normalized transcript、chunk、minutes JSON/Markdown、visual contextを置く。
- Cosmos DB: Functions VNet Integration と Private Endpoint / Private DNS 経由にして、到達性検証後に public network access を無効化する。
- AI Services: Speech/CUのURL fetch制約があるため、この段階ではprivate化しない。

この対策は完全閉域化ではない。Ingest Storageのpublic endpointは残るが、匿名公開とShared Keyは無効のまま、User Delegation SASの短TTLと限定CORSで保護する。

### 2.4 Function registration

- Azure上は v1 `function.json` wrappers を使い、Python 3.13環境で安定して関数をindexさせる。
- `function_app.py` はローカル・テスト用であり、`.funcignore` によりデプロイパッケージから除外する。
- Flex Consumption はPython 3.13 package indexingが安定しなかったため、dev MVPでは Functions Premium EP1 を採用した。

## 3. 処理フロー

### 3.1 ジョブ作成

1. UIが `POST /api/jobs` を呼ぶ。
2. APIは jobId を採番する。
3. APIは `raw-audio/{tenantId}/{jobId}/{safeFileName}` のBlobパスを決める。`safeFileName` はパストラバーサル、制御文字、過度に長い名前、PII混入を避けるために正規化した名前にする。
4. APIは write 権限だけの短時間 User Delegation SAS を発行する。
5. APIは Cosmos DB にジョブ状態 `CREATED` を保存する。
6. APIは jobId と uploadUrl を返す。

### 3.2 直接アップロード

1. UIが uploadUrl に対してファイルをPUTする。
2. アップロード進捗をUIに表示する。
3. 完了後、UIが `POST /api/jobs/{jobId}/upload-complete` を呼ぶ。
4. APIは Blob の存在とサイズを確認し、ジョブ状態を `UPLOADED` にする。
5. APIは Durable Functions orchestration を開始し、`202 Accepted` を返す。

### 3.3 文字起こし

1. Orchestrator が `ValidateJobInput` を実行する。
2. 処理方式ごとの入力上限を評価する。標準経路の直接Speech入力は500MB未満、m4a/mp4など前処理対象の元ファイルは4GB未満、Content Understanding動画理解（実験）経路は4GB未満、いずれも120分以下。前処理後FLACが500MB以上ならFast Transcription投入前に失敗にする。
3. Fast Transcription に `definition.audioUrl` を送る。本番経路では inline `audio` を使わない。
4. `definition` には `locales: ["ja-JP"]` と `diarization` を含める。
5. `channels` は指定しない。diarization有効時に stereo の `[0,1]` 指定はしない。
6. Speech API の raw response を Artifact Storage（分離前のdev MVPでは既存Storage）に保存する。

### 3.4 議事録生成

1. raw response を normalized transcript に変換する。
2. 本線では normalized transcript全文を `GenerateFinalMinutesActivity` がArtifact Storage（分離前のdev MVPでは既存Storage）から読み込む。
3. `minutes.structured-output.schema.json` に準拠する JSON を1回のStructured outputs呼び出しで生成する。
4. アプリ側で metadata を付与し、`minutes.schema.json` で保存前検証を行う。
5. direct生成が出力切れ、token制約、schema repair不能などで失敗した場合だけ、chunk summary方式へ自動fallbackする。
6. Markdownをアプリコードで生成する。

### 3.5 結果取得とユーザーレビュー

1. UIは `GET /api/jobs/{jobId}` をポーリングする。
2. transcript ready後、`GET /api/jobs/{jobId}/transcript` で正規化済みtranscriptを取得する。
3. minutes ready後、`GET /api/jobs/{jobId}/minutes` で議事録を取得する。
4. UIは speaker ごとの代表発話を表示する。
5. ユーザーは `Speaker 0 = 山田` のように紐付ける。
6. 議事録の話者表示を更新する。
7. 必要なら最終議事録だけ再生成する。

## 4. コンポーネント設計

### 4.1 Frontend

責務:

- ファイル選択。
- 拡張子とサイズの事前チェック。
- ブラウザで可能なら音声長の事前チェック。
- Direct-to-Blob upload。
- ジョブ状態ポーリング。
- transcript 表示。
- speaker mapping 入力。
- 議事録表示とダウンロード。

推奨:

- React + TypeScript + Vite。
- API client は OpenAPI から生成してもよい。
- 状態管理は初期実装では React Query または SWR 程度にする。
- ポーリングは固定短間隔ではなく、`CREATED` / `TRANSCRIBING` / `GENERATING_*` など状態ごとにbackoffを調整する。

### 4.2 API Functions

責務:

- 認証済みユーザーの job 作成。
- User Delegation SAS 発行。
- upload-complete 受付。
- job status 取得。
- transcript / minutes 取得API。
- speaker mapping 更新。

2026-06-01時点のdev MVPでは、job作成、upload-complete、status、transcript取得、minutes取得が実装・live smoke済み。speaker mapping更新、再生成、retry、job一覧はPhase 2以降。

### 4.3 Durable Functions

責務:

- 長時間処理のオーケストレーション。
- リトライ。
- custom status 更新。
- direct minutes generation と、必要時のchunk fallback。

OrchestratorではI/Oを直接行わず、I/OはActivityに閉じ込める。各Activityは固定Blob pathを使い、同じ入力の再実行で破壊的副作用が起きないようにする。

### 4.4 Speech Client

責務:

- Fast Transcription REST API 呼び出し。
- keyless authentication を優先する。
- 429/5xx/ネットワークエラーの指数バックオフ。
- 400/401/422などのクライアントエラーは再試行しない。
- `audioUrl` 用SASの有効期限がSpeech fetchとretry中に切れないようにする。

### 4.5 Minutes Generator

責務:

- normalized transcript全文からのdirect minutes生成。
- 必要時のtranscript chunk生成とchunk summary fallback。
- Structured outputs 用schemaによる制御と保存用JSON Schema検証。
- Markdown変換。

UIでは議事録生成モデルを選択できる。既定の「高速」は `gpt-5.4-mini`、「高品質」は `gpt-5.4` を使う。両deploymentはGlobalStandard capacity 100でデプロイ済み。`temperature` 等の生成パラメーターはdeployment capabilityに基づいて送る。

direct minutes generationは長尺音声でJSON出力が切れないよう `max_completion_tokens=32768` と `reasoning_effort=low` を使う。429が継続する場合はcapacity、選択モデル、fallback発動状況、prompt量を見直す。

### 4.6 Storage Repository

責務:

- Blob への保存・読み取り。
- SAS発行。
- m4a/mp4から音声トラックをFast Transcription用の16kHz mono FLACへ前処理し、Speechが読む入力として public ingest Storage の `preprocessed/{tenantId}/{jobId}/input.flac` に保存する。
- Cosmos DB への job state 保存。
- 同一 jobId の冪等性保証。

## 5. Azure Functions と Container Apps の使い分け

初期実装は Azure Functions + Durable Functions で開始し、dev MVPは Functions Premium EP1 で稼働している。

dev MVPではm4a/mp4前処理をFunctions Activity内で `imageio-ffmpeg` の同梱ffmpegバイナリをsubprocess実行して行う。Functions Premium EP1で動作確認済みだが、依存バイナリのサイズ、実行権限、タイムアウト、サプライチェーンレビューは本番化時に確認する。より重い変換やffprobe検証が必要になった場合だけ、Azure Container Apps Jobs を追加する。

## 6. 進捗通知方式

### Phase 1: Polling

- UIが `GET /api/jobs/{jobId}` を呼ぶ。
- Durable Functions custom status と Cosmos DB の状態を返す。
- 実装が簡単でPoC向き。
- 429やバックエンド負荷を避けるため、状態が長く変わらない場合は間隔を広げる。

### Phase 2: Azure SignalR Service

- 状態変化時にサーバーからクライアントへpushする。
- 多数ユーザーやリアルタイム性が必要になったら追加する。

## 7. 可用性と冪等性

- `upload-complete` は同じjobIdで複数回呼ばれても安全にする。
- Orchestrator instanceId は jobId と一致させる。
- 既に `DONE` のジョブは再処理しない。
- 将来的には `FAILED` のジョブを `retry` API 経由で再実行する。
- 各Activityは入力と出力Blobパスを固定し、再実行しても同じ場所に同じ形式で保存する。

dev MVPではretry APIは未実装のため、既に `FAILED` になったジョブは同じファイルを再アップロードして新規ジョブとして実行する。

## 8. 認証・セキュリティ上の本番化ブロッカー

現在のdev MVPは `MEETING_MINUTES_AUTH_MODE=demo` の固定tenant/userで動く。Azure環境では `x-dev-tenant-id` / `x-dev-user-id` を信用しないが、HTTP trigger + demo認証は本番・実データ・広範な共有利用には使わない。

本番化前の必須条件:

1. Microsoft Entra ID / Easy Auth をFrontend/APIで強制する。
2. token claims から tenantId / userId を取得する。
3. job所有者・tenant境界の認可テストを追加する。
4. anonymous HTTP triggerに直接到達しても業務APIが処理されないことを確認する。

## 9. 将来拡張

| 拡張 | 条件 |
|---|---|
| LLM Speech 比較 | Fast Transcription の固有名詞精度に不満がある場合 |
| Content Understanding 比較 | 音声・動画・資料を同一基盤で処理したい場合 |
| Batch Transcription | 即時性より大量処理を優先する場合 |
| SignalR | ポーリング負荷や体感UXが課題になった場合 |
| Azure AI Search | 過去議事録横断検索が必要になった場合 |
