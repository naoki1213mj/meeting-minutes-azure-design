# 12. Copilot CLI で実装を始めるための手順

確認日: 2026-06-01

## 結論

Copilot CLIには、最初に「設計理解だけ」をさせる。いきなり実装させない。理解確認が合ってから、`.github/prompts/` の順に小さく実装する。

## 1. 最初のプロンプト

```text
まず @AGENTS.md と @.github/copilot-instructions.md と @README.md を読んでください。
このリポジトリの目的、初期実装の本線、実装順序を日本語で要約してください。
まだファイル変更はしないでください。
```

確認ポイント:

- 全体音声を Fast Transcription に1回投入する、と説明できているか。
- 音声チャンク並列文字起こしを初期実装しない、と説明できているか。
- Fast Transcription本番経路で `definition.audioUrl` を使う、と説明できているか。
- Azure OpenAI v1 APIを使う、と説明できているか。
- Structured outputs用schemaと保存用schemaを分ける、と説明できているか。

## 2. 最初の実装プロンプト

```text
@.github/prompts/01-bootstrap-repo.prompt.md を実行してください。
実装前に、作成・変更するファイル一覧と理由を提示してください。
その計画を rubber-duck agent でレビューし、指摘と採否を提示してください。
私が承認するまでファイル変更はしないでください。
```

## 3. 2つ目以降の進め方

1タスクずつ実装する。

```text
@.github/prompts/02-backend-api.prompt.md を実行してください。
実装前に、変更計画とテスト方針を提示してください。
変更前に rubber-duck agent で計画レビューを行い、指摘と採否を提示してください。
```

同じように、`03`、`04`、`05` の順で進める。

## 4. Copilotへの共通確認

各タスクの最後に、次を確認させる。

```text
今回のタスクで rubber-duck agent をどう使い、どの指摘を採用/不採用にしたかを書いてください。
今回の変更が docs/ と specs/ に矛盾していないか確認してください。
実行したテスト・lint・typecheckを列挙してください。
実行できなかった確認があれば、理由と代替確認を書いてください。
```

## 5. 実装前品質ゲート

実装、設計変更、仕様変更、テスト追加、インフラ変更など、PJ成果物の意味を変えるタスクでは、毎回 rubber-duck agent を使う。特に次の変更では、実装前に計画をレビューさせる。

- 新規ファイル作成
- API handler、Durable Orchestrator、Activity、Azure SDK呼び出しの追加・変更
- JSON Schema、OpenAPI、Cosmos DB data model、job status enumの変更
- 認証、SAS、RBAC、managed identity、ログ設計の変更
- Bicep、Azure Developer CLI、CI/CD、Python runtime、依存関係の変更

実装前に確認する項目:

- Fast Transcription は全体音声1回投入で、音声チャンク並列文字起こしをしていない。
- diarization 有効時に `channels` を指定していない。
- Fast Transcription 本番経路で `definition.audioUrl` を使っている。
- `upload-complete` は `202 Accepted` を返し、長時間処理をHTTP同期で待っていない。
- Orchestrator内でI/O、現在時刻取得、乱数生成を直接行っていない。
- Activityが冪等で、同じjobIdの再実行で破壊的副作用がない。
- job status は `specs/job-status.schema.json` のenumだけを使っている。
- OpenAPIの `JobStatus` は `specs/job-status.schema.json` を参照し、`JobStatusEnum` はJSON Schemaのstatus enumと一致している。
- Blob pathに元ファイル名をそのまま入れず、`safeFileName` またはcanonical nameを使っている。
- Structured outputs に `specs/minutes.schema.json` を渡していない。
- 最終保存前のminutesを `specs/minutes.schema.json` で検証している。
- 音声本文、transcript全文、minutes全文、SAS URL全文、token、keyをログに出していない。
- Python 3.13でAzure Functionsと主要依存が解決できることを確認している。
- Storage account keyを使ったSAS発行を実装していない。

## 6. 危ない出力が出た場合の止め方

次のような提案が出たら差し戻す。

- 音声をチャンク分割して並列に Fast Transcription へ投げる。
- Speech APIに inline `audio` で80分音声を送る。
- Azure OpenAI呼び出しに `AZURE_OPENAI_API_VERSION` を足す。
- `specs/minutes.schema.json` をStructured outputsに直接渡す。
- SAS URLやtranscript全文をログに出す。
- speaker IDから実名を自動推定する。

差し戻しプロンプト例:

```text
その実装案は設計方針と違います。
@AGENTS.md と @docs/11-review-findings-2026-05-31.md を読み直し、
矛盾している点を列挙してから、修正版の実装計画だけを提示してください。
まだファイル変更はしないでください。
```
