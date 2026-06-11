# Minutes Studio

[![CI](https://github.com/naoki1213mj/meeting-minutes-azure-design/actions/workflows/ci.yml/badge.svg)](https://github.com/naoki1213mj/meeting-minutes-azure-design/actions/workflows/ci.yml)

## 録音を、読める議事録へ。

Minutes Studio は、録音済み音声ファイルから **話者分離付き transcript** と **読みやすい議事録** を非同期に生成する Azure ベースの開発 MVP です。ブラウザから音声を直接アップロードし、Azure Speech in Foundry Tools と Azure OpenAI in Microsoft Foundry Models を組み合わせて、根拠 timestamp 付きの議事録 JSON / Markdown を生成します。

> **現在の状態:** dev MVP です。`MEETING_MINUTES_AUTH_MODE=demo` を使うデモ認証が残っているため、Microsoft Entra ID / Easy Auth とユーザー単位認可へ置き換えるまでは **production-ready ではありません**。実データ・機密音声・広範な共有利用には使わないでください。

## このリポジトリの位置づけ

このリポジトリは、録音済み会議ファイルから議事録を生成するAzureアーキテクチャの **参考実装** です。特に、次のような課題を整理するためのリファレンスとして使えます。

- 音声を細かく分割して逐次文字起こしする構成が遅い。
- 話者分離付き議事録で、speaker ID の一貫性を保ちたい。
- 長時間処理をHTTP同期で待たず、ジョブとして非同期に進めたい。
- 議事録生成の根拠 timestamp と schema validation を残したい。
- Azure上で、入力用Storageと成果物Storageのセキュリティ境界を分けたい。

本線は **標準経路 = Azure Speech in Foundry Tools Fast Transcription + diarization → Azure OpenAI in Microsoft Foundry Models で議事録生成** です。Fast上限を超える長尺・大容量入力は、標準経路内で Batch Transcription へ自動切替します。Content Understanding動画理解は、映像補足を確認したい場合だけ明示的に選ぶ実験経路です。

## 顧客共有時の注意

- GitHubリポジトリは公開安全版です。実Azureリソース名、subscription/tenant ID、実endpoint、SAS URL、token/key、実音声/transcript/minutes本文は含めない方針です。
- WebアプリURLはデモ用参考として共有できますが、**dev MVP** です。顧客には実データ・機密音声をアップロードしない前提で案内してください。
- デモ用アクセスキーを使う場合、アプリURLとは別の安全な経路で共有してください。共有デモは期間・対象者を限定し、非機密サンプル音声だけを使ってください。
- デモ用アクセスキーやプロキシシークレットはREADMEやIssueに書かないでください。共有後に必要に応じてローテーションしてください。
- 公開Issue / Pull Request / 画面共有には、音声本文、transcript全文、議事録全文、SAS URL、トークン、API key、実リソース名を載せないでください。

## 何ができるか

- 録音済み音声をジョブとして登録し、長時間処理を HTTP 同期で待たずに進める。
- ブラウザから Azure Blob Storage へ直接アップロードする。
- 全体音声を Azure Speech in Foundry Tools Fast Transcription に 1 回だけ渡し、diarization を有効にする。
- Fast上限を超えるがBatch上限内の入力は、Batch Transcriptionへ自動fallbackする。
- transcript は、原則として全文を 1 回の Structured outputs 呼び出しに渡して議事録を生成する。
- 長大入力や出力切れなど direct 生成で回復可能な制約に当たった場合だけ、transcriptテキストのchunk summary方式へ自動fallbackする。
- Structured outputs で議事録 JSON を生成し、保存前に JSON Schema で検証する。
- Markdown は LLM に直接書かせず、検証済み JSON からアプリコードで生成する。
- speaker ID は匿名ラベルとして扱い、実名はユーザー入力の speaker mapping で更新する。

## 価値提案

- **待ち時間を見える化:** アップロード、文字起こし、議事録生成の進捗をジョブ状態として追跡します。
- **話者の一貫性を優先:** 音声チャンクごとの並列文字起こしを避け、speaker ID の分断を減らします。
- **速度と品質を選択:** 議事録生成は高速（GPT-5.4-mini）と高品質（GPT-5.4）をジョブごとに選べます。
- **根拠を残す:** 決定事項、ToDo、未決事項、リスクに timestamp を残します。
- **推測しない:** transcript にない事実、担当者、期限、参加者名を補完しません。
- **Azure 標準構成:** Azure Functions、Durable Functions、Blob Storage、Cosmos DB、Microsoft Foundry project、Application Insights、Bicep を中心に構成します。
- **アプリ内で説明完結:** 右サイドドロワーの「仕組みガイド」で、処理内容、Batch fallback、動画理解（実験）、Azure構成、保護方針をデモ中に確認できます。

## dev MVP の実装範囲

実装済みの主経路:

| 機能 | 状態 |
|---|---|
| `POST /api/jobs` によるジョブ作成とアップロード URL 発行 | dev MVP 実装済み |
| ブラウザから Blob Storage への直接アップロード | dev MVP 実装済み |
| `POST /api/jobs/{jobId}/upload-complete` による workflow 開始 | `202 Accepted` を返す |
| Durable Functions による非同期処理 | dev MVP 実装済み |
| Fast Transcription + diarization | 全体音声 1 回の本線で実装 |
| transcript 正規化と schema validation | dev MVP 実装済み |
| transcript全文からの direct minutes JSON / Markdown 生成 | dev MVP 実装済み |
| chunk summary方式 | direct生成の自動fallbackとして保持 |
| Content Understanding動画理解経路 | 実験経路。MP4の映像補足を取得・表示 |
| `GET /api/jobs/{jobId}` / transcript / minutes 取得 | dev MVP 実装済み |

Phase 2 以降の候補:

- Microsoft Entra ID / Easy Auth とユーザー単位認可。
- speaker mapping 更新 API / UI の拡充。
- job 一覧、retry、cancel、regenerate の運用機能。
- 代表音声 fixture による E2E 回帰テスト。
- 進捗 push 通知、過去議事録検索、重い音声前処理の分離。

## アーキテクチャ概要

```text
React + Vite Web UI / App Service
  -> POST /api/jobs
  -> Azure Functions API
  -> User Delegation SAS
  -> Public Ingest Storage へブラウザから直接アップロード
  -> POST /api/jobs/{jobId}/upload-complete
  -> Durable Functions orchestration
  -> Azure Speech in Foundry Tools Fast Transcription + diarization
     or Batch Transcription fallback
  -> normalized transcript
  -> Azure OpenAI in Microsoft Foundry Models v1 API
  -> direct minutes JSON generation
  -> final minutes JSON schema validation
  -> Markdown rendering
  -> Private Artifact Storage / Cosmos DB / Application Insights
```

重要な設計制約:

- 音声チャンクごとの並列文字起こしは初期実装では行いません。
- 最大120分までの議事録生成は、transcript全文を使う direct 生成を本線にします。
- chunk summary は本線ではなく、direct 生成が出力切れなどで失敗した場合の fallback として扱います。
- diarization 有効時に `channels` は指定しません。
- Fast Transcription の本番経路では `audioUrl` を使います。inline `audio` は小さい開発・検証用に限定します。
- Azure OpenAI in Microsoft Foundry Models は v1 API を使い、新規に dated `api-version` を追加しません。
- `temperature` などの生成パラメーターは全モデルに固定送信せず、deployment capability に基づいて送ります。

## リポジトリ構成

| パス | 内容 |
|---|---|
| `backend/` | Python 3.13 のAzure Functions / Durable Functions backend。HTTP API、Activity、service/repository層、テストを含みます。 |
| `frontend/` | React + TypeScript + Vite のWeb UI。アップロード、進捗表示、結果表示、仕組みガイドを含みます。 |
| `infra/` | Bicep + Azure Developer CLI 用IaC。App Service、Functions、Storage、Cosmos DB、AIServices、Private Endpointなどを定義します。 |
| `specs/` | OpenAPI 3.1 と JSON Schema。API契約、normalized transcript、minutes、Structured outputs用schemaを管理します。 |
| `docs/` | 要件、設計、workflow、セキュリティ、運用、ビジネスユーザー/エンジニア向け説明資料。 |
| `docs/diagrams/` | draw.io図と顧客説明用PDF。公開安全なラベルだけを使います。 |
| `docs/adr/` | Architecture Decision Records。主要な設計判断を記録します。 |
| `scripts/` | spec validationなど、リポジトリ検証用スクリプト。 |
| `.github/` | Copilot instructions、CI workflow、Issue/PRテンプレート。 |

## 対応形式と制限

| 項目 | dev MVP の扱い |
|---|---|
| 受理する拡張子 | `.mp3`, `.wav`, `.m4a`, `.mp4`, `.ogg`, `.webm`, `.flac` |
| `application/octet-stream` | 上記拡張子に限って受理 |
| MP4 | 動画から音声トラックだけを抽出して前処理 |
| 標準経路の直接音声入力上限 | 1GB 未満。500MB超または2時間超はBatch fallback |
| 標準経路のm4a/mp4元ファイル上限 | 4GB 未満。抽出後音声がFast上限超ならBatch fallback、Batch上限超なら失敗 |
| 動画理解（実験）経路の上限 | 4GB 未満（Blob URL参照のCU経路のみ） |
| 音声長 | 標準経路は4時間未満までBatch fallback候補。動画理解（実験）は120分未満 |
| m4a / mp4 | 必要に応じて backend で 16kHz mono FLAC へ前処理 |

Fast Transcription の diarization 経路は 2 時間境界に近づくほど失敗リスクが高くなります。Fast上限を超える標準経路入力は、1GB未満・4時間未満ならBatch Transcription fallbackへ自動切替します。動画理解（実験）経路の大容量動画はブロック分割アップロードを使い、アップロードSAS TTLを長めにしますが、ネットワーク中断時は再実行が必要です。

## セキュリティとプライバシー

- 本番化前に Microsoft Entra ID / Easy Auth を必須化し、token claims に基づく tenant/user 認可へ切り替えます。
- SAS は User Delegation SAS を使い、Storage account key を使った SAS は新規実装しません。
- SAS は用途ごとにTTLと権限を分けます。アップロードSASは短時間、Batch入力のread SASは処理待ちを考慮して長めに発行します。
- Blob 匿名公開と共有キーアクセスは無効化します。
- azd既定デプロイ（`infra/main.parameters.json`）では、Private Endpoint疎通検証済みのdev環境を前提に、Speech/CUが読む入力は public network endpoint を維持した Ingest Storage に限定し、transcript / minutes / visual context などの artifact は Private Endpoint 経由の別Storageへ分離します。
- Ingest Storageのpublic network endpointは、ブラウザ直接アップロードとSpeech/CUのURL fetch制約のため維持します。ただし匿名公開ではなく、短期TTLのUser Delegation SAS / Entra ID を前提にします。
- Cosmos DB は Functions VNet Integration + Private Endpoint 経由にし、public network accessを無効化する構成をazd既定デプロイで有効化しています。既存public構成から段階移行する場合は、先にPrivate Endpoint疎通を確認してからpublic accessを閉じてください。
- 音声本文、transcript 全文、議事録全文、SAS URL 全文、アクセストークン、API key、Storage account key をログに出しません。
- speaker ID から実名を自動推定しません。
- 脆弱性報告は `SECURITY.md` を参照してください。公開 Issue に秘密情報や実データを貼らないでください。

## クイックスタート

### 前提ツール

- Python 3.13
- uv
- Node.js 20
- Azure CLI
- Azure Developer CLI (`azd`)
- Azure サブスクリプションと、必要な Azure RBAC を付与できる権限

### リポジトリ取得

```powershell
git clone <repository-url>
cd meeting-minutes-azure-design
```

### ローカル設定

```powershell
Copy-Item .env.example .env
```

`.env` にはローカル検証用の値だけを設定してください。Azure の実リソース名、SAS URL、API key、トークンをコミットしないでください。

### Azure Developer CLI 環境

```powershell
azd env new dev --no-prompt
azd env set AZURE_SUBSCRIPTION_ID "<subscription-id>"
azd env set AZURE_LOCATION "<azure-region>"
azd env set AZURE_PRINCIPAL_ID "<principal-object-id>"
```

#### 顧客デモのアクセスキー（任意）

顧客デモでは、URL を知られても合言葉なしでは利用できないように、共有キーでアプリ全体をゲートできます（詳細は `SECURITY.md`）。デプロイ前に、互いに異なる強いランダム値を 2 つ設定します。

```powershell
# 顧客に教える合言葉（ログイン画面で入力）
azd env set AZURE_DEMO_ACCESS_KEY "<long-random-key>"
# フロントエンド→Functions 間の内部シークレット（ブラウザには出ない・別の値）
azd env set AZURE_PROXY_SECRET "<another-long-random-secret>"
```

- 顧客には「アプリの URL」と「合言葉（`AZURE_DEMO_ACCESS_KEY` の値）」だけを伝えます。
- これらの値はコミットしないでください。未設定のまま Azure にデプロイすると、ゲートは fail-closed（503）になります。
- ローカル開発では未設定で構いません（ゲートは無効化されます）。

デプロイ手順と本番化ゲートは `docs/13-deployment-plan.md` を確認してください。

## 開発・テストコマンド

バックエンド:

```powershell
cd backend
uv sync
uv run pytest
uv run ruff check .
uv run mypy .
uv run python ..\scripts\validate_specs.py
```

フロントエンド:

```powershell
cd frontend
npm install
npm run typecheck
npm test
npm run build
```

インフラ:

```powershell
az bicep build --file infra\main.bicep
```

スキーマ確認のみ:

```powershell
python -m json.tool specs\minutes.schema.json > $null
python -m json.tool specs\minutes.structured-output.schema.json > $null
python -m json.tool specs\chunk-summary.structured-output.schema.json > $null
python -m json.tool specs\normalized-transcript.schema.json > $null
```

## ドキュメント索引

- `docs/diagrams/azure-resource-architecture.drawio` - Azureサービスアイコン付きリソース構成図。
- `docs/diagrams/azure-network-architecture.drawio` - public ingest と Private Endpoint / Private DNS の境界を示すネットワーク構成図。
- `docs/diagrams/azure-architecture.drawio` - シンプルなAzureアーキテクチャ概要図。
- `docs/diagrams/minutes-studio-azure-diagrams.pdf` - 顧客説明向けに3つの構成図をまとめたPDF。
- `docs/00-design-summary.md` - 設計サマリーと現在の dev MVP 状態。
- `docs/01-requirements.md` - 要件。
- `docs/02-architecture.md` - アーキテクチャ。
- `docs/03-api-spec.md` - API 設計。
- `docs/04-data-model.md` - データモデル。
- `docs/05-workflow-spec.md` - Durable Functions workflow。
- `docs/06-ai-and-prompts.md` - AI 処理とプロンプト方針。
- `docs/07-security-and-operations.md` - セキュリティと運用。
- `docs/08-implementation-plan.md` - 実装計画。
- `docs/09-test-plan.md` - テスト計画。
- `docs/10-official-references.md` - 公式リファレンス。
- `docs/11-review-findings-2026-05-31.md` - レビュー結果。
- `docs/12-copilot-cli-vibe-coding-guide.md` - Copilot CLI 作業ガイド。
- `docs/13-deployment-plan.md` - 公開安全なデプロイ計画と runbook。
- `docs/14-business-user-processing-guide.md` - ビジネスユーザー向けの処理説明。
- `docs/15-azure-engineer-processing-guide.md` - Azureエンジニア向けの処理方式・運用説明。
- `docs/adr/` - Architecture Decision Records。ADR-008でpublic ingest + private artifactsの中期ネットワーク方針を記録。
- `specs/openapi.yaml` - OpenAPI 3.1 契約。
- `specs/*.schema.json` - JSON Schema / Structured outputs schema。

## ロードマップ

1. Microsoft Entra ID / Easy Auth、demo 認証廃止、ユーザー単位認可テスト。
2. 代表的な短い会議音声 fixture と品質期待値の整備。
3. 80分級・2時間超・Batch fallback経路の性能、コスト、429率の測定とADR化。
4. UI ポーリング backoff、retry、cancel、regenerate、job 一覧の整備。
5. Application Insights での機密ログ漏えい回帰スキャン自動化。
6. 必要に応じて Azure SignalR Service、Azure AI Search、Azure Container Apps Jobs を追加。

## コントリビュート

`CONTRIBUTING.md` を参照してください。Issue や Pull Request には、音声本文、transcript、議事録全文、SAS URL、トークン、API key、実リソース名を含めないでください。

## ライセンス

このリポジトリは MIT License です。詳細は `LICENSE` と `LICENSE-NOTES.md` を参照してください。
