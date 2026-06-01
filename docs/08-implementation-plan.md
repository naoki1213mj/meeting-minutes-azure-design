# 08. 実装計画

確認日: 2026-06-01

## 1. 実装方針

GitHub Copilot CLIで進めやすいよう、タスクを小さく分ける。各タスクは、実装、テスト、README更新を1セットにする。

実装に入る前に、`docs/12-copilot-cli-vibe-coding-guide.md` の実装前品質ゲートを確認する。特に schema/OpenAPI整合、job status enum、Blob path、機密ログ、RBAC、Durable Functions制約、Python 3.13依存解決は先に潰す。

### Python runtime

- バックエンドは Python 3.13 を既定にする。
- Azure Functions runtime は v4 を使う。
- 2026-06-01時点で Azure Functions の Python 3.13 はGA。Python 3.14 はPreviewのため初期実装では採用しない。
- Durable Functions SDK、Azure SDK、Pydantic、OpenAI SDK、HTTP clientなど主要依存が Python 3.13 で動くことをPhase 0で確認する。
- Python 3.13採用判断は `docs/adr/006-python-313-runtime.md` を正とする。Python 3.14検討履歴は `docs/adr/005-python-314-runtime.md` に残す。

## 2. Phase 0: リポジトリ準備

### 目的

最小のモノレポ構成を作る。

### 作業

- `backend/` を Python 3.13 + uv + Azure Functions として作る。
- `frontend/` を React + TypeScript + Vite として作る。
- `infra/` に Bicep を置く。
- `specs/` を正として、APIとJSON Schemaを参照する。
- CIで lint/test/schema validation を実行する。
- `specs/job-status.schema.json` と `specs/openapi.yaml` の `JobStatusEnum` が一致する検査をCIに入れる。
- Python 3.13で `azure-functions`, `azure-functions-durable`, `azure-cosmos`, `azure-storage-blob`, `azure-identity`, `openai` など主要依存が解決できることを確認する。
- Flex Consumption、Functions Premium、またはコンテナー化のうち、Python 3.13で使うホスティング/デプロイ方式をPhase 0で決め、未確定のままAPI実装へ進まない。
- 2026-06-01の実デプロイでは、Flex ConsumptionのPython 3.13 package indexingが安定しなかったため、初期MVPのBackend hostingは Functions Premium EP1 とする。Azure上のHTTP関数は v1 `function.json` wrapperで登録し、`function_app.py` はローカルテスト用として `.funcignore` でデプロイ対象外にする。

### 完了条件

- `uv run pytest` が成功する。
- `npm test` または `npm run typecheck` が成功する。
- OpenAPIとJSON Schemaがリポジトリに存在する。
- Python 3.13で主要依存の解決確認が完了している。
- Python 3.13で使うAzure Functionsのホスティング/デプロイ方式が決まっている。
- job status enumの整合性検査が成功する。

## 3. Phase 1: API基本実装

### 対象API

- `POST /api/jobs`
- `POST /api/jobs/{jobId}/upload-complete`
- `GET /api/jobs/{jobId}`

### 作業

- Cosmos DB repository を作る。
- Blob SAS issuer を作る。
- User Delegation SAS を使う。
- jobId は ULID を推奨する。
- upload-complete で Durable orchestration を開始する。

### 完了条件

- API単体テストがある。
- Cosmos DB/Blobはローカルテストでモック可能。
- 同じ `upload-complete` を2回呼んでも二重実行しない。

## 4. Phase 2: Durable workflow

### 作業

- Orchestratorを作る。
- Activityを最低限実装する。
  - LoadJob
  - ValidateInput
  - CreateReadSas
  - TranscribeAudio: 最初はスタブ可
  - NormalizeTranscript: 最初はサンプル入力で実装
  - GenerateChunkSummaries: 最初はスタブ可
  - GenerateFinalMinutes: 最初はスタブ可
  - CompleteJob / FailJob

### 完了条件

- サンプル transcript で `DONE` まで進む。
- custom status が更新される。
- 失敗時に `FAILED` になる。

## 5. Phase 3: Speech client

### 作業

- Fast Transcription REST client を実装する。
- keyless authentication 優先で実装する。
- API key fallback は `.env` 設定がある場合のみ許可する。
- `definition.audioUrl`, `locales`, `diarization` を送る。本番経路で inline `audio` は使わない。
- raw response を Blob に保存する。
- retry policy を実装する。

### 完了条件

- 実音声または小さなテスト音声で transcription が成功する。
- speaker ID を含む response を保存できる。
- 429/5xxのリトライ単体テストがある。

## 6. Phase 4: Transcript normalization

### 作業

- Speech response から normalized transcript を生成する。
- `specs/normalized-transcript.schema.json` で検証する。
- speakerごとの代表発話を抽出する。

### 完了条件

- サンプル raw response からスキーマ準拠JSONを生成できる。
- `Speaker 0` 等のラベルが安定している。
- timestamp表示が `HH:MM:SS` で出る。

## 7. Phase 5: 議事録生成

### 作業

- transcript chunker を実装する。
- chunk summary prompt を実装する。
- final merge prompt を実装する。
- Structured outputs を使う。LLM呼び出しには `specs/*.structured-output.schema.json` を使う。
- JSON Schema検証と1回の修復を実装する。
- Markdown renderer を実装する。

### 完了条件

- サンプル transcript から Structured outputs 用schema準拠のLLM応答を生成できる。
- metadata付与後に `minutes.schema.json` 準拠の minutes を保存できる。
- Markdownがコードで生成される。
- transcriptにない担当者・期限を推測しないテストがある。

## 8. Phase 6: Frontend

### 作業

- ファイル選択画面。
- サイズ・拡張子の事前チェック。
- direct upload。
- progress表示。
- transcript表示。
- speaker mapping UI。
- minutes表示。

### 完了条件

- 80分想定ファイルのアップロード進捗を表示できる。
- transcript ready時点で画面に文字起こしを表示できる。
- speaker mappingを保存できる。
- minutesをMarkdown表示できる。

## 9. Phase 7: Observability

### 作業

- Application Insights を有効化する。
- custom metrics を出す。
- Durable Functions distributed tracing を有効化する。
- ログに本文やSASが出ないことを確認する。

### 完了条件

- jobIdで全Activityの処理時間を追える。
- 失敗原因をダッシュボードで確認できる。
- 音声本文・transcript全文・SASがログに出ない。

## 10. Phase 8: Infra

### 作業

- Bicepでリソースを定義する。
- RBACを定義する。
- managed identity を構成する。
- `azd up` または GitHub Actions でデプロイできるようにする。

### 完了条件

- 開発環境に一括デプロイできる。
- アプリ設定が Key Vault または App Settings で管理される。
- Storage account key をアプリ設定に置かない。

## 11. Copilot CLIでの推奨順序

`.github/prompts/` の順番で実行する。

```text
01-bootstrap-repo.prompt.md
02-backend-api.prompt.md
03-durable-workflow.prompt.md
04-speech-client.prompt.md
05-minutes-generation.prompt.md
06-frontend.prompt.md
07-tests-and-observability.prompt.md
08-azure-integration-smoke-test.prompt.md
```

## 12. 実装時の判断ルール

- 仕様と矛盾する場合は仕様を優先する。
- Azure公式仕様と矛盾する場合は公式仕様を優先し、`docs/adr/` に記録する。
- 動くものを急ぐ場合でも、本文データをログに出してはいけない。
- LLM出力は Structured outputs 用schemaで制御し、保存前に app schema で検証する。
- まず標準経路を通す。LLM Speech、Batch、Content Understandingは後回し。
