# AGENTS.md

このリポジトリは、Azure上で録音済み音声から話者分離付き議事録を生成するシステムです。Copilot CLI またはエージェントは、このファイルと `.github/copilot-instructions.md` を必ず参照して作業してください。

## 最初に読むファイル

1. `README.md`
2. `docs/00-design-summary.md`
3. `docs/02-architecture.md`
4. `docs/05-workflow-spec.md`
5. `docs/06-ai-and-prompts.md`
6. `specs/openapi.yaml`
7. `specs/chunk-summary.structured-output.schema.json`
8. `specs/minutes.structured-output.schema.json`
9. `specs/minutes.schema.json`
10. `specs/normalized-transcript.schema.json`

## 守るべき本線

- 初期実装では、音声チャンク並列文字起こしを実装しない。
- 文字起こしは、全体音声を Azure Speech in Foundry Tools Fast Transcription に1回投入する。
- diarization を必ず有効にする。
- `channels` は指定しない。diarization 有効時に stereo の `[0,1]` 指定をしてはいけない。
- 議事録生成だけを transcript チャンクで並列化する。
- Fast Transcription の本番経路では `audioUrl` を使い、inline `audio` は小さい開発・検証用に限定する。
- Azure OpenAI in Microsoft Foundry Models は v1 API を使い、dated `api-version` を新規追加しない。
- `temperature` などの生成パラメーターは全モデルに固定送信しない。deploymentごとのcapability設定に基づいて送る。
- MarkdownはLLMに直接書かせず、minutes JSONからコードで生成する。

## レビュー運用

- 実装、設計変更、仕様変更、テスト追加、インフラ変更など、PJ成果物の意味を変える各タスクでは、実装前の計画レビューまたは変更後レビューとして rubber-duck agent を毎回使う。
- rubber-duck の指摘、採用した対応、採用しなかった判断理由を最終報告に含める。
- 仕様、スキーマ、API、認証、SAS、RBAC、Durable Functions、Azure SDK呼び出しに関わる変更では、必ず実装前に rubber-duck で計画を確認する。

## 技術スタック

- Python 3.13
- uv
- Azure Functions Python
- Durable Functions
- Azure Blob Storage
- Azure Cosmos DB for NoSQL
- Azure Speech in Foundry Tools
- Azure OpenAI in Microsoft Foundry Models
- React + TypeScript + Vite
- Bicep

## 作業コマンドの想定

バックエンド:

```bash
cd backend
uv sync
uv run pytest
uv run ruff check .
uv run mypy .
```

フロントエンド:

```bash
cd frontend
npm install
npm run typecheck
npm test
npm run build
```

全体:

```bash
python -m json.tool specs/minutes.schema.json > /dev/null
python -m json.tool specs/minutes.structured-output.schema.json > /dev/null
python -m json.tool specs/chunk-summary.structured-output.schema.json > /dev/null
python -m json.tool specs/normalized-transcript.schema.json > /dev/null
```

まだ該当コマンドが存在しない場合は、実装タスクの中で追加してください。

## 実装ルール

- 仕様は `docs/` と `specs/` を正とする。
- Python 3.13 を既定にする。Azure Functions runtime v4 のGAサポートを前提にし、Python 3.14へ上げる場合はPreview制約を再確認してADRを更新する。
- APIレスポンスは `specs/openapi.yaml` に合わせる。
- Structured outputs のLLM呼び出しには `specs/*.structured-output.schema.json` だけを渡す。
- app保存前の最終議事録は `specs/minutes.schema.json` で必ず検証する。
- `specs/minutes.schema.json` は `format`, `pattern`, `minItems` を含むため、Structured outputs に直接渡してはいけない。
- transcript出力は `specs/normalized-transcript.schema.json` で必ず検証する。
- Azure SDK呼び出しは service/repository 層に閉じ込める。
- Orchestrator内でネットワークI/OやファイルI/Oを直接行わない。I/OはActivityに置く。
- 各Activityは冪等に実装する。同じ入力で再実行しても破壊的副作用が起きないようにする。
- エラーはユーザー向けメッセージと内部詳細を分ける。

## セキュリティ禁止事項

- 音声本文をログに出さない。
- transcript全文をログに出さない。
- 議事録全文をログに出さない。
- SAS URL全文をログに出さない。
- アクセストークン、Storage account key、API key をログに出さない。
- Storage account key を使ったSASを新規実装しない。User Delegation SAS を使う。
- speaker ID から個人を自動識別しようとしない。

## 命名規則

- Python: snake_case
- TypeScript: camelCase
- React component: PascalCase
- Azure resource symbolic names: lower camelCase
- Blob path: kebab-caseまたはlowercase
- job status: UPPER_SNAKE_CASE

## 失敗時の扱い

- 429/5xx/network error は retry policy に従う。
- 400/401/422などのクライアントエラーは原則リトライしない。
- `FAILED` へ遷移するときは `error.code`, `error.message`, `correlationId` を保存する。
- ユーザー向けエラーは短く、具体的にする。

## 実装の進め方

`.github/prompts/` の順に1ファイルずつ作業してください。各タスクでは、次を必ず行ってください。

1. rubber-duck agent に計画または変更内容をレビューさせる。
2. 変更対象ファイルを最小化する。
3. テストを追加する。
4. 仕様と矛盾しないか確認する。
5. 実行可能なテスト・lint・typecheckを実行する。
6. 実行できない場合は理由と代替確認を記録する。

## 判断に迷った場合

- まず公式ドキュメントを確認する。
- 仕様と公式が矛盾する場合は公式を優先する。
- 設計判断を変える場合は `docs/adr/` にADRを追加する。
- 初期実装を複雑にする案は、Phase 2以降に分離する。
