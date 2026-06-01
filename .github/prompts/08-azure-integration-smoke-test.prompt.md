# Task 08: Add Azure integration smoke test plan

Azure実リソースへ接続する前の smoke test と、接続後の最小疎通確認を追加してください。

## 参照する仕様

- `docs/05-workflow-spec.md`
- `docs/06-ai-and-prompts.md`
- `docs/07-security-and-operations.md`
- `docs/11-review-findings-2026-05-31.md`
- `AGENTS.md`

## 実装対象

1. `docs/runbooks/local-smoke-test.md`
2. `docs/runbooks/azure-smoke-test.md`
3. backend の mock-based smoke test
4. Azure接続時の手順書

## ルール

- 実音声やtranscript全文をログに出さない。
- Speech本番経路は `definition.audioUrl` を使う。
- Azure OpenAIは v1 API を使う。
- Structured outputsには `specs/*.structured-output.schema.json` を使う。
- smoke test 用の音声は小さいサンプルに限定する。

## 完了条件

- mock環境で job create -> upload-complete -> workflow mock -> minutes mock まで通る。
- Azure接続時に必要なRBAC、環境変数、確認コマンドが文書化されている。
- 失敗時の切り分け観点が文書化されている。
