# 06. AI処理・プロンプト仕様

確認日: 2026-06-01

## 1. AI処理の責務分離

| 処理 | サービス | 目的 |
|---|---|---|
| 音声文字起こし | Azure Speech in Foundry Tools Fast Transcription | speaker ID と timestamp 付き transcript |
| チャンク要約 | Azure OpenAI in Microsoft Foundry Models v1 API | 5〜10分単位の論点抽出 |
| 最終統合 | Azure OpenAI in Microsoft Foundry Models v1 API | 議事録JSON生成 |
| Markdown生成 | アプリコード | JSONから確定的に生成 |

## 2. モデル選定

dev MVPでは AIServices `<ai-services-name>` に `gpt-5.4-mini` と `gpt-5.4` をGlobalStandard capacity 100でデプロイしている。

推奨設定:

```text
chunk summary: gpt-5.4-mini
final merge: gpt-5.4
structured outputs: enabled
```

理由:

- GPT-5.4 mini は chunk summary の第一候補にする。
- GPT-5.4 は final merge の品質確認候補にする。
- capacity 1および10ではlive smokeのfinal mergeで429が発生したため、dev MVPでは両deploymentをcapacity 100へ増強した。
- 55分m4a音声のfinal mergeでJSON出力切れが発生したため、final mergeは `max_completion_tokens=32768` と `reasoning_effort=low` を使う。`finish_reason=length` やcontent filterは本文を保存せず診断理由だけを残す。
- GPT-4.1 mini / GPT-4o は、Regional/Data residencyやコスト比較が必要な場合の比較軸として残す。

注意: GPT-5系の一部モデルでは、モデルごとに利用できるパラメーターが異なる。`temperature` 等を固定で送らず、deploymentごとのcapability設定に基づいてrequestを組み立てる。また、リージョン・デプロイ種別・quota tier により利用可否が変わるため、本番既定化前に対象サブスクリプションで実デプロイ可否、Structured outputs対応、入出力トークン上限、Global/Regional/Data Zone のデータ処理場所を確認する。

## 3. Azure OpenAI API 方針

新規実装では Azure OpenAI in Microsoft Foundry Models の **v1 API** を使う。

```text
base_url: https://<resource-name>.openai.azure.com/openai/v1/
client: openai.OpenAI
api-version: 使わない
```

Microsoft Entra ID を使う場合は、`DefaultAzureCredential` と bearer token provider を使う。API key はローカル検証のfallbackに限定する。

## 4. Schema の使い分け

Structured outputs には、Azure OpenAI の対応subsetに収まる schema だけを渡す。

| 用途 | ファイル | 使い方 |
|---|---|---|
| chunk summary のLLM出力制御 | `specs/chunk-summary.structured-output.schema.json` | Structured outputs に渡す |
| final minutes のLLM出力制御 | `specs/minutes.structured-output.schema.json` | Structured outputs に渡す |
| 保存前の最終検証 | `specs/minutes.schema.json` | app側で jobId, tenantId, generatedAt 等を付与して検証 |
| transcript保存前検証 | `specs/normalized-transcript.schema.json` | Speech response正規化後に検証 |

重要: `specs/minutes.schema.json` は app 保存用の厳密schemaであり、`format`、`pattern`、`minItems` を含む。Structured outputs に直接渡してはいけない。

## 5. 重要な生成ルール

- transcript にない事実を作らない。
- 担当者、期限、決定事項を推測で補わない。
- 不明な担当者は `owner: null` にする。
- 不明な期限は `dueDate: null` にする。
- 根拠 timestamp を必ず入れる。
- speaker ID は speaker mapping がない限り `Speaker 0` などのまま使う。
- 顧客名や固有名詞は transcript の表記を尊重する。
- 迷う内容は `openQuestions` または `risks` に入れる。
- transcript全文、chunk summary全文、minutes全文をログに出さない。

## 6. Transcript chunk input

chunk summary に渡す入力は次の形に整える。

```json
{
  "meetingTitle": "顧客定例会",
  "locale": "ja-JP",
  "chunkIndex": 0,
  "timeRange": {
    "start": "00:00:00",
    "end": "00:10:00"
  },
  "speakerMapping": [
    {"speakerLabel": "Speaker 0", "displayName": null},
    {"speakerLabel": "Speaker 1", "displayName": null}
  ],
  "phrases": [
    {
      "startTime": "00:00:12",
      "speakerLabel": "Speaker 0",
      "text": "本日のアジェンダは..."
    }
  ]
}
```

## 7. Chunk summary system prompt

```text
あなたは企業会議の議事録作成を支援するアシスタントです。
入力は、話者ラベルとタイムスタンプ付きの文字起こしです。

以下を守ってください。
- 入力にない事実を作らない。
- 決定事項、ToDo、期限、担当者を推測で補わない。
- 不明な担当者は null にする。
- 不明な期限は null にする。
- 根拠となる timestamp を sourceTimestamps または evidenceTimestamps に入れる。
- speakerLabel は入力どおり使う。実名を推測しない。
- 出力は指定された Structured outputs schema に厳密に従う。
```

## 8. Chunk summary user prompt

```text
次の transcript chunk から、議事録の材料を抽出してください。

抽出対象:
1. 論点
2. 決定事項
3. ToDo
4. 未決事項
5. リスク・懸念
6. 重要な引用 timestamp

transcript chunk:
{chunk_json}
```

## 9. Final merge system prompt

```text
あなたは企業会議の議事録編集者です。
複数の chunk summary を統合し、重複を取り除き、読みやすい議事録 JSON を作成します。

以下を守ってください。
- chunk summary にない事実を追加しない。
- 同じ決定事項やToDoは統合する。
- 明示されていない担当者や期限は null のままにする。
- timestamp は根拠として残す。
- 出力は指定された Structured outputs schema に厳密に従う。
```

## 10. Final merge user prompt

```text
以下の chunk summary を統合して、最終議事録を作成してください。

会議タイトル: {meeting_title}
会議日時: {meeting_datetime_or_null}
speaker mapping: {speaker_mapping_json}
chunk summaries: {chunk_summaries_json}
```

## 11. LLM response enrichment and validation

1. Chunk summary 応答は `specs/chunk-summary.structured-output.schema.json` で制御する。
2. Final merge 応答は `specs/minutes.structured-output.schema.json` で制御する。
3. アプリ側で `jobId`, `tenantId`, `generatedAt`, `model` を付与する。
4. 保存前に `specs/minutes.schema.json` で検証する。
5. 検証失敗時は、修復プロンプトを1回だけ実行する。
6. 修復に失敗した場合は `MINUTES_SCHEMA_VALIDATION_FAILED` とする。

## 12. 修復プロンプト

```text
前回の出力は保存用JSON Schemaに適合しませんでした。
以下のバリデーションエラーを修正し、同じ内容を保ったまま、指定されたJSON Schemaに適合するJSONのみを返してください。

validation errors:
{validation_errors}

invalid output:
{invalid_json}
```

## 13. Markdown rendering

MarkdownはLLMに生成させず、アプリコードで minutes JSON から生成する。これにより、表記揺れを減らし、再生成時の差分を小さくする。

出力例:

```markdown
# {title}

## 概要
{summary}

## 論点
### {topic.title}
{topic.discussion}

## 決定事項
- {decision.text}（根拠: {timestamp}）

## ToDo
| タスク | 担当 | 期限 | 根拠 |
|---|---|---|---|
| ... | ... | ... | ... |

## 未決事項
- ...
```

## 14. 評価観点

PoCでは以下を人手で評価する。

| 観点 | 評価方法 |
|---|---|
| 固有名詞 | transcript と議事録を比較 |
| 決定事項の抜け | 人手議事録と比較 |
| ToDoの正しさ | 担当者・期限・内容を確認 |
| 不要な推測 | transcript にない内容が入っていないか確認 |
| speaker mapping | 実名紐付け後の読みやすさを確認 |
| 処理時間 | transcription seconds、chunk summary seconds、final merge seconds、total secondsを計測 |
| 429耐性 | retryCount、backoff、capacity、並列度を確認 |

## 15. 禁止事項

- transcript にない参加者名を推測しない。
- speaker ID から個人を識別しようとしない。
- 期限を「来週」などから勝手に日付化しない。日付化する場合は別途ルール化する。
- 顧客名や機密情報をログに出さない。
- `temperature` などの生成パラメーターを全deploymentへ固定送信しない。
