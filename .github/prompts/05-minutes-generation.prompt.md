# Task 05: Implement minutes generation

normalized transcript から議事録JSONとMarkdownを生成する処理を実装してください。

## 参照する仕様

- `docs/06-ai-and-prompts.md`
- `specs/chunk-summary.structured-output.schema.json`
- `specs/minutes.structured-output.schema.json`
- `specs/minutes.schema.json`
- `specs/normalized-transcript.schema.json`
- `AGENTS.md`

## 実装対象

1. transcript chunker
2. chunk summary prompt builder
3. final merge prompt builder
4. Azure OpenAI v1 API client interface
5. Structured outputs 用 request builder
6. JSON Schema validation
7. validation失敗時の修復1回
8. Markdown renderer

## ルール

- Azure OpenAI in Microsoft Foundry Models は v1 API を使う。`AZURE_OPENAI_API_VERSION` は使わない。
- `temperature` などの生成パラメーターは全モデルに固定送信しない。deploymentごとのcapability設定に基づいて送る。
- Structured outputs には `specs/chunk-summary.structured-output.schema.json` と `specs/minutes.structured-output.schema.json` を使う。
- `specs/minutes.schema.json` は保存前検証用であり、LLM呼び出しに直接渡さない。
- MarkdownはLLMに生成させず、minutes JSONからコードで生成する。
- transcriptにない担当者・期限・決定事項を推測しない。
- 不明な担当者は `null`。
- 不明な期限は `null`。
- timestampを保持する。

## テスト

- sample transcript から chunks が生成される。
- structured-output schema準拠のLLM応答が作れる。
- app側でmetadata付与後、`specs/minutes.schema.json` のvalidationが通る。
- invalid JSON の修復が1回だけ呼ばれる。
- Markdown renderer が安定した出力を返す。
- 推測禁止のケースをテストする。
