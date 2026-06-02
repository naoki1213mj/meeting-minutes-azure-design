# 06. AI処理・プロンプト仕様

確認日: 2026-06-01

## 1. AI処理の責務分離

| 処理 | サービス | 目的 |
|---|---|---|
| 音声文字起こし | Azure Speech in Foundry Tools Fast Transcription | speaker ID と timestamp 付き transcript |
| direct議事録生成 | Azure OpenAI in Microsoft Foundry Models v1 API | normalized transcript全文から議事録JSON生成 |
| chunk fallback | Azure OpenAI in Microsoft Foundry Models v1 API | direct生成が出力切れ等で失敗した場合の分割生成 |
| Markdown生成 | アプリコード | JSONから確定的に生成 |

## 2. モデル選定

dev MVPでは AIServices `<ai-services-name>` に `gpt-5.4-mini` と `gpt-5.4` をGlobalStandard capacity 100でデプロイしている。

推奨設定:

```text
minutes direct fast: gpt-5.4-mini
minutes direct quality: gpt-5.4
chunk fallback summary: gpt-5.4-mini
structured outputs: enabled
```

理由:

- UIでは「高速」を既定にし、GPT-5.4 miniで待ち時間を短縮する。
- UIでは「高品質」を選べるようにし、GPT-5.4で重要会議の品質確認に使う。
- chunk summary方式は本線ではなく、direct生成が出力切れ・token制約・schema repair不能等で失敗した場合のfallbackにする。
- capacity 1および10ではlive smokeのfinal mergeで429が発生したため、dev MVPでは両deploymentをcapacity 100へ増強した。
- 55分m4a音声の旧final mergeでJSON出力切れが発生したため、direct minutes generation / fallback final merge は `max_completion_tokens=32768` と `reasoning_effort=low` を使う。`finish_reason=length` やcontent filterは本文を保存せず診断理由だけを残す。
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

## 6. Direct minutes input

最大120分までの本線では、normalized transcript全文を1回のStructured outputs呼び出しに渡す。Activity間のpayloadやDurable historyにはtranscript本文を載せず、`GenerateFinalMinutesActivity` がBlobから読み込んでLLMへ渡す。

```json
{
  "meetingTitle": "顧客定例会",
  "locale": "ja-JP",
  "durationMilliseconds": 3330005,
  "speakers": [
    {"speakerLabel": "Speaker 0", "displayName": null},
    {"speakerLabel": "Speaker 1", "displayName": null}
  ],
  "phrases": [
    {
      "startTime": "00:00:12",
      "endTime": "00:00:15",
      "speakerLabel": "Speaker 0",
      "text": "本日のアジェンダは..."
    }
  ]
}
```

## 7. Direct minutes system prompt

```text
あなたは企業会議の議事録編集者です。
normalized transcriptだけを根拠に、正確で読みやすい議事録JSONを作成してください。

以下を守ってください。
- 入力にない事実を作らない。
- 決定事項、ToDo、期限、担当者を推測で補わない。
- 不明な担当者は null にする。
- 不明な期限は null にする。
- 根拠となる timestamp を sourceTimestamps または evidenceTimestamps に入れる。
- speakerLabel は入力どおり使う。実名を推測しない。
- 出力は指定された Structured outputs schema に厳密に従う。
```

## 8. Direct minutes user prompt

```text
以下の normalized transcript 全文から、最終議事録を作成してください。

会議タイトル: {meeting_title}
会議日時: null

厳守事項:
- transcriptにない事実を追加しない。
- 決定事項、担当者、期限を推測で補わない。
- 不明な担当者はnull、不明な期限はnullにする。
- 根拠となるsourceTimestamps/evidenceTimestampsを必ず残す。
- speakerLabelから実名を自動推定しない。
- displayNameがnullの場合はspeakerLabelをそのまま扱う。

normalized transcript:
{normalized_transcript_json}
```

## 9. Chunk fallback

direct生成で次のような回復可能な制約に当たった場合だけ、既存のchunk summary方式へ自動fallbackする。

- LLM応答が `finish_reason=length` 相当で切り詰められた。
- direct生成のJSONが壊れており、schema repairでは回復できない。
- 入力tokenまたは出力tokenの制約に当たった。

fallback時は `BuildTranscriptChunksActivity` / `GenerateChunkSummaryActivity` と同等のchunk summary処理を使い、最終的に `specs/minutes.schema.json` で保存前検証する。fallback発動はApplication Insightsに `minutesGenerationMode=chunk_fallback` として記録し、transcript全文・prompt全文・minutes全文はログに出さない。

## 10. LLM response enrichment and validation

1. Direct minutes 応答は `specs/minutes.structured-output.schema.json` で制御する。
2. Chunk fallback のchunk summary応答は `specs/chunk-summary.structured-output.schema.json` で制御する。
3. アプリ側で `jobId`, `tenantId`, `generatedAt`, `model` を付与する。
4. 保存前に `specs/minutes.schema.json` で検証する。
5. 検証失敗時は、修復プロンプトを1回だけ実行する。
6. 修復に失敗した場合は `MINUTES_SCHEMA_VALIDATION_FAILED` とする。

## 11. 修復プロンプト

```text
前回の出力は保存用JSON Schemaに適合しませんでした。
以下のバリデーションエラーを修正し、同じ内容を保ったまま、指定されたJSON Schemaに適合するJSONのみを返してください。

validation errors:
{validation_errors}

invalid output:
{invalid_json}
```

## 12. Markdown rendering

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

## 13. 評価観点

PoCでは以下を人手で評価する。

| 観点 | 評価方法 |
|---|---|
| 固有名詞 | transcript と議事録を比較 |
| 決定事項の抜け | 人手議事録と比較 |
| ToDoの正しさ | 担当者・期限・内容を確認 |
| 不要な推測 | transcript にない内容が入っていないか確認 |
| speaker mapping | 実名紐付け後の読みやすさを確認 |
| 処理時間 | transcription seconds、direct minutes seconds、fallback発動有無、total secondsを計測 |
| 429耐性 | retryCount、backoff、capacity、並列度を確認 |

## 15. 禁止事項

- transcript にない参加者名を推測しない。
- speaker ID から個人を識別しようとしない。
- 期限を「来週」などから勝手に日付化しない。日付化する場合は別途ルール化する。
- 顧客名や機密情報をログに出さない。
- `temperature` などの生成パラメーターを全deploymentへ固定送信しない。
