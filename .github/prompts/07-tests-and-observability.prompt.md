# Task 07: Tests and observability

テストと監視の実装を強化してください。

## 参照する仕様

- `docs/07-security-and-operations.md`
- `docs/09-test-plan.md`
- `AGENTS.md`

## 作業内容

1. backendの単体テストを増やす。
2. frontendのコンポーネントテストを増やす。
3. Application Insights / OpenTelemetry の設定を追加する。
4. custom metrics helper を実装する。
5. 機密ログ禁止のテストを追加する。
6. GitHub Actions CIを追加する。

## 必須メトリック

- `meeting.transcription.seconds`
- `meeting.chunk_summary.seconds`
- `meeting.final_merge.seconds`
- `meeting.total.seconds`
- `meeting.speech.retry_count`
- `meeting.openai.prompt_tokens`
- `meeting.openai.completion_tokens`

## 完了条件

- CIで backend lint/test と frontend typecheck/test が動く。
- jobIdで処理を追える。
- 音声本文、transcript全文、SAS URL全文、token、key がログに出ないことをテストする。
