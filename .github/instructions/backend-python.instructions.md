---
applyTo: "backend/**/*.py"
---

# Backend Python instructions

- Python 3.13 を前提にする。Azure Functions runtime v4 のGAサポートを前提にし、Python 3.14へ上げる場合はPreview制約を再確認してADRを更新する。
- パッケージ管理は uv を使う。
- すべての公開関数に型ヒントを付ける。
- 外部I/Oは service/repository 層に分離する。
- Durable Functions の Orchestrator 内ではネットワークI/O、Blob/Cosmosアクセス、現在時刻取得、乱数生成を直接行わない。
- Activityは冪等にする。
- API入力はPydanticモデルで検証する。
- エラーは `AppError(code, message, details)` のようなアプリ共通例外に正規化する。
- ログに音声本文、transcript全文、minutes全文、SAS URL全文、token、key を出さない。
- テストは pytest で書く。
- Azure SDKは単体テストでモックできるようにラップする。
- Fast Transcription の本番経路では `definition.audioUrl` を使う。80分音声を inline `audio` で送らない。
- Azure OpenAI in Microsoft Foundry Models は v1 API と `openai.OpenAI` client を使う。dated `api-version` を追加しない。
- Structured outputs には `specs/*.structured-output.schema.json` を使う。`specs/minutes.schema.json` は保存前検証用。
