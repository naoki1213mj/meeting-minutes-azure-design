# Minutes Studio

[![CI](https://github.com/naoki1213mj/meeting-minutes-azure-design/actions/workflows/ci.yml/badge.svg)](https://github.com/naoki1213mj/meeting-minutes-azure-design/actions/workflows/ci.yml)

## 録音を、読める議事録へ。

Minutes Studio は、録音済み音声ファイルから **話者分離付き transcript** と **読みやすい議事録** を非同期に生成する Azure ベースの開発 MVP です。ブラウザから音声を直接アップロードし、Azure Speech in Foundry Tools と Azure OpenAI in Microsoft Foundry Models を組み合わせて、根拠 timestamp 付きの議事録 JSON / Markdown を生成します。

> **現在の状態:** dev MVP です。`MEETING_MINUTES_AUTH_MODE=demo` を使うデモ認証が残っているため、Microsoft Entra ID / Easy Auth とユーザー単位認可へ置き換えるまでは **production-ready ではありません**。実データ・機密音声・広範な共有利用には使わないでください。

## 何ができるか

- 録音済み音声をジョブとして登録し、長時間処理を HTTP 同期で待たずに進める。
- ブラウザから Azure Blob Storage へ直接アップロードする。
- 全体音声を Azure Speech in Foundry Tools Fast Transcription に 1 回だけ渡し、diarization を有効にする。
- 最大120分までの transcript は、原則として全文を 1 回の Structured outputs 呼び出しに渡して議事録を生成する。
- 長大入力や出力切れなど direct 生成で回復可能な制約に当たった場合だけ、chunk summary 方式へ自動 fallback する。
- Structured outputs で議事録 JSON を生成し、保存前に JSON Schema で検証する。
- Markdown は LLM に直接書かせず、検証済み JSON からアプリコードで生成する。
- speaker ID は匿名ラベルとして扱い、実名はユーザー入力の speaker mapping で更新する。

## 価値提案

- **待ち時間を見える化:** アップロード、文字起こし、議事録生成の進捗をジョブ状態として追跡します。
- **話者の一貫性を優先:** 音声チャンクごとの並列文字起こしを避け、speaker ID の分断を減らします。
- **速度と品質を選択:** 議事録生成は高速（GPT-5.4-mini）と高品質（GPT-5.4）をジョブごとに選べます。
- **根拠を残す:** 決定事項、ToDo、未決事項、リスクに timestamp を残します。
- **推測しない:** transcript にない事実、担当者、期限、参加者名を補完しません。
- **Azure 標準構成:** Azure Functions、Durable Functions、Blob Storage、Cosmos DB、Application Insights、Bicep を中心に構成します。

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
React + Vite Web UI
  -> POST /api/jobs
  -> Azure Functions API
  -> User Delegation SAS
  -> Azure Blob Storage へ直接アップロード
  -> POST /api/jobs/{jobId}/upload-complete
  -> Durable Functions orchestration
  -> Azure Speech in Foundry Tools Fast Transcription + diarization
  -> normalized transcript
  -> Azure OpenAI in Microsoft Foundry Models v1 API
  -> direct minutes JSON generation
  -> final minutes JSON schema validation
  -> Markdown rendering
  -> Blob Storage / Cosmos DB / Application Insights
```

重要な設計制約:

- 音声チャンクごとの並列文字起こしは初期実装では行いません。
- 最大120分までの議事録生成は、transcript全文を使う direct 生成を本線にします。
- chunk summary は本線ではなく、direct 生成が出力切れなどで失敗した場合の fallback として扱います。
- diarization 有効時に `channels` は指定しません。
- Fast Transcription の本番経路では `audioUrl` を使います。inline `audio` は小さい開発・検証用に限定します。
- Azure OpenAI in Microsoft Foundry Models は v1 API を使い、新規に dated `api-version` を追加しません。
- `temperature` などの生成パラメーターは全モデルに固定送信せず、deployment capability に基づいて送ります。

## 対応形式と制限

| 項目 | dev MVP の扱い |
|---|---|
| 受理する拡張子 | `.mp3`, `.wav`, `.m4a`, `.mp4`, `.ogg`, `.webm`, `.flac` |
| `application/octet-stream` | 上記拡張子に限って受理 |
| MP4 | 動画から音声トラックだけを抽出して前処理 |
| 通常受付サイズ | 300MB 未満 |
| ハード上限 | 500MB 未満 |
| 音声長 | 120分まで best effort。120分超は拒否 |
| m4a / mp4 | 必要に応じて backend で 16kHz mono FLAC へ前処理 |

Fast Transcription の diarization 経路は 2 時間境界に近づくほど失敗リスクが高くなります。120分近傍は best effort とし、公開・本番利用の前に対象リージョン、SKU、quota、データ所在地、代表音声での品質・処理時間・コストを確認してください。

## セキュリティとプライバシー

- 本番化前に Microsoft Entra ID / Easy Auth を必須化し、token claims に基づく tenant/user 認可へ切り替えます。
- SAS は User Delegation SAS を使い、Storage account key を使った SAS は新規実装しません。
- SAS は短い TTL と最小権限で発行します。
- Blob 匿名公開と共有キーアクセスは無効化する方針です。
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
- `docs/diagrams/azure-architecture.drawio` - シンプルなAzureアーキテクチャ概要図。
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
- `docs/adr/` - Architecture Decision Records。
- `specs/openapi.yaml` - OpenAPI 3.1 契約。
- `specs/*.schema.json` - JSON Schema / Structured outputs schema。

## ロードマップ

1. Microsoft Entra ID / Easy Auth、demo 認証廃止、ユーザー単位認可テスト。
2. 代表的な短い会議音声 fixture と品質期待値の整備。
3. 80 分級音声を含む性能・コスト・429 率の測定と ADR 化。
4. UI ポーリング backoff、retry、cancel、regenerate、job 一覧の整備。
5. Application Insights での機密ログ漏えい回帰スキャン自動化。
6. 必要に応じて Azure SignalR Service、Azure AI Search、Azure Container Apps Jobs を追加。

## コントリビュート

`CONTRIBUTING.md` を参照してください。Issue や Pull Request には、音声本文、transcript、議事録全文、SAS URL、トークン、API key、実リソース名を含めないでください。

## ライセンス

このリポジトリは MIT License です。詳細は `LICENSE` と `LICENSE-NOTES.md` を参照してください。
