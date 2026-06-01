# GitHub Copilot custom instructions

このリポジトリでは、日本語で説明し、コード・設定ファイル・コメントは必要に応じて英語でもよい。ただしユーザー向け文言、README、設計メモは日本語で書く。

## プロジェクト概要

Azure上で、録音済み音声ファイルから話者分離付きの文字起こしと議事録を生成するシステムを作る。初期実装は、全体音声を Azure Speech in Foundry Tools Fast Transcription に1回投入し、diarization を有効にする。音声チャンク並列文字起こしは初期実装では行わない。議事録生成だけを transcript チャンクで並列化する。

## 正式名称

- Microsoft Foundry
- Azure Speech in Foundry Tools
- Azure OpenAI in Microsoft Foundry Models
- Azure Functions
- Durable Functions
- Azure Blob Storage
- Azure Cosmos DB for NoSQL
- Azure Monitor Application Insights
- Azure AI Search

「Azure AI Foundry」という旧名称は使わない。公式ドキュメント名やURLに含まれる場合だけ例外とする。

## 技術スタック

- Backend: Python 3.13, uv, Azure Functions, Durable Functions
- Frontend: TypeScript, React, Vite
- Infra: Bicep
- Test: pytest, ruff, mypy, npm test/typecheck
- Schemas: JSON Schema 2020-12, OpenAPI 3.1

## アーキテクチャ制約

- Python 3.13 を既定にする。Azure Functions runtime v4 のGAサポートを前提にし、Python 3.14へ上げる場合はPreview制約を再確認してADRを更新する。
- 長時間処理はHTTP同期で待たず、Durable Functionsで非同期処理にする。
- `upload-complete` API は `202 Accepted` を返す。
- ユーザーはBlob Storageへ直接アップロードする。
- SASはUser Delegation SASを使う。
- Orchestrator内でI/Oを直接行わない。
- Activityは冪等にする。
- Structured outputs のLLM呼び出しには `specs/*.structured-output.schema.json` だけを使う。
- 最終保存前のminutesは `specs/minutes.schema.json` で検証する。
- Fast Transcription の本番経路では `audioUrl` を使う。inline `audio` は小さい開発・検証用に限定する。
- Azure OpenAI in Microsoft Foundry Models は v1 API を使い、dated `api-version` を新規追加しない。
- `temperature` などの生成パラメーターは全モデルに固定送信しない。deploymentごとのcapability設定に基づいて送る。

## AI処理ルール

- transcript にない事実を議事録に追加しない。
- 決定事項、担当者、期限を推測で補わない。
- 不明な担当者は `null` にする。
- 不明な期限は `null` にする。
- 根拠 timestamp を残す。
- speaker ID から実名を自動推定しない。
- speaker mapping はユーザー入力で更新する。

## セキュリティルール

- 音声本文、transcript全文、議事録全文、SAS URL全文、アクセストークン、API key、Storage account key をログに出さない。
- APIエラーはユーザー向けmessageと内部detailsを分ける。
- managed identity と Microsoft Entra ID を優先する。
- Storage account keyを使ったSASを新規実装しない。

## コード品質

- 型ヒントを書く。
- 境界では Pydantic などで入力検証する。
- Azure SDK呼び出しは薄いservice/repository層へ分離する。
- テストしやすいように外部依存をinterface化する。
- マジックナンバーは設定に切り出す。
- タイムスタンプはUTC ISO 8601で扱う。
- 例外は握りつぶさない。

## 変更時の確認

- `docs/` と `specs/` に矛盾しないこと。
- JSON Schema validation が通ること。
- テストが追加または更新されていること。
- ログに機密データが出ないこと。
- Azure公式情報と違う実装にする場合はADRを追加すること。
