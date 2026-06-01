# 11. 再精査結果と修正方針

確認日: 2026-05-31

## 結論

前版の大きな設計方針は維持する。つまり、初期実装は **全体音声を Fast Transcription + diarization に1回投入し、議事録生成だけを transcript チャンクで並列化する**。

ただし、実装時に事故りやすい点があったため、次を修正した。

## 1. Structured outputs 用schemaと保存用schemaを分離した

### 前版の問題

前版では、`specs/minutes.schema.json` を Structured outputs に渡す前提の記述があった。

これは危険。Azure OpenAI Structured outputs は JSON Schema のsubsetのみをサポートする。`format`、`pattern`、`minItems`、`maxItems` などのtype-specific keywordsは使えない。また、objectのすべてのfieldをrequiredにする必要がある。

一方、`specs/minutes.schema.json` は保存前の厳密検証用として、`format`、`pattern`、`minItems` を使っている。そのため、LLM呼び出しに直接渡すschemaとしては不適切。

### 修正

以下を追加した。

- `specs/chunk-summary.structured-output.schema.json`
- `specs/minutes.structured-output.schema.json`

使い分けは次の通り。

```text
LLM呼び出し:
  specs/chunk-summary.structured-output.schema.json
  specs/minutes.structured-output.schema.json

保存前の最終検証:
  specs/minutes.schema.json
```

実装では、LLM応答にアプリ側で `jobId`, `tenantId`, `generatedAt`, `model` を付与してから `minutes.schema.json` で検証する。

## 2. Azure OpenAI v1 API を明示した

### 前版の問題

`.env.example` に `AZURE_OPENAI_API_VERSION=2025-04-01-preview` が残っていた。新規実装では、dated `api-version` 前提の古い呼び出しに寄せる理由が弱い。

### 修正

`.env.example` を次の方針に変更した。

```text
AZURE_OPENAI_BASE_URL=https://<resource-name>.openai.azure.com/openai/v1/
AZURE_OPENAI_API_VERSION は使わない
```

Copilot向け指示にも、Azure OpenAI in Microsoft Foundry Models は v1 API を使うことを明記した。

## 3. Fast Transcription の本番経路を audioUrl に固定した

### 前版の問題

Fast Transcription の公式例には inline `audio` も載っている。前版も `audioUrl` 方針ではあったが、「本番では inline を使わない」という制約がまだ弱かった。

80分音声のような大きいファイルでは、APIサーバーが音声を受け取ってSpeech APIへ再送信すると、二重転送になりUXが悪くなる。また REST APIのinline `audio` には別のサイズ制限があるため、本番経路にすると詰まりやすい。

### 修正

次を明記した。

- 本番経路では `definition.audioUrl` を使う。
- inline `audio` は小さい開発・検証用に限定する。
- `audioUrl` の読み取りSAS TTLは、Speechサービスのfetchとretryが終わるまで有効にする。初期値は90分。

## 4. 完全閉域構成を初期PoCから外した

### 前版の問題

`audioUrl` 方式は、SpeechサービスがBlob URLに到達できる必要がある。厳格なPrivate Endpoint構成では、この点が要件とぶつかる可能性がある。

### 修正

初期PoCは public endpoint + 短時間SAS + Entra ID/RBAC を前提にした。完全閉域は別設計とし、初期UX短縮の主経路には入れない。

理由は、完全閉域で音声をWorker経由にすると二重転送になり、inline uploadの制限も絡むため、低レイテンシ要件と相性が悪いから。

## 5. Copilot CLI 向けの制約を強化した

### 前版の問題

`AGENTS.md` と `.github/copilot-instructions.md` はよくできていたが、Structured outputs のschema分離、Azure OpenAI v1 API、Fast Transcription audioUrl固定が十分に強く書かれていなかった。

### 修正

次を追加した。

- LLM呼び出しには `specs/*.structured-output.schema.json` だけを使う。
- `specs/minutes.schema.json` をStructured outputsに直接渡さない。
- Azure OpenAIはv1 APIを使う。
- Fast Transcription本番経路は `definition.audioUrl` にする。

## 採用しなかった変更

### 音声チャンク並列文字起こし

採用しない。speaker IDの統合が重く、初期実装の価値に対してリスクが大きい。

### Batch Transcriptionの主経路化

採用しない。ピーク時の待ち時間がUX要件に合わない。

### MAI-Transcribe-1の利用

採用しない。diarization非対応のため、今回の主要件に合わない。

### Content Understandingの主経路化

採用しない。将来比較候補として残す。初期実装では Fast Transcription と Azure OpenAI の明示的なパイプラインのほうが制御しやすい。

## 6. モデル既定値を GPT-4.1 系から GPT-5.4 系へ寄せた

### 前版の問題

前版では、速度優先で GPT-4.1 / GPT-4.1 mini を第一候補にしていた。モデル選択ガイド上は低レイテンシ用途に合っているが、2026-05-31時点の公式retirement scheduleでは GPT-4.1系は 2026-10-14 にretirement予定である。

短期PoCなら比較対象として有用だが、これを本番既定値にすると、実装直後に移行計画が必要になる。

### 修正

`.env.example` の既定値を次に変更した。

```text
AZURE_OPENAI_DEPLOYMENT_CHUNK_SUMMARY=gpt-5.4-mini
AZURE_OPENAI_DEPLOYMENT_FINAL_MERGE=gpt-5.4
```

GPT-4.1系は比較候補として残すが、本番化を見据えた既定値にはしない。

## 実装で最初に見るべきファイル

```text
README.md
AGENTS.md
.github/copilot-instructions.md
docs/05-workflow-spec.md
docs/06-ai-and-prompts.md
specs/chunk-summary.structured-output.schema.json
specs/minutes.structured-output.schema.json
specs/minutes.schema.json
```
