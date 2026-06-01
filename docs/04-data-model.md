# 04. データモデル設計

確認日: 2026-06-01

## 1. 保存方針

- 音声ファイル、raw transcript、normalized transcript、minutes は Blob Storage に保存する。
- ジョブ状態、メタデータ、speaker mapping、action items は Cosmos DB に保存する。
- 大きな本文を Cosmos DB に保存しない。Cosmos DB には Blob URI と短い概要だけを保存する。
- 個人情報や音声本文をログに出さない。

## 2. Blob Storage レイアウト

```text
raw-audio/{tenantId}/{jobId}/{safeFileName}
transcript/raw/{tenantId}/{jobId}/speech-response.json
transcript/normalized/{tenantId}/{jobId}/normalized-transcript.json
minutes/json/{tenantId}/{jobId}/minutes.v{version}.json
minutes/markdown/{tenantId}/{jobId}/minutes.v{version}.md
minutes/chunks/{tenantId}/{jobId}/chunk-{index}.json
artifacts/{tenantId}/{jobId}/exports/{fileName}
```

`safeFileName` はBlob path専用の正規化済みファイル名で、`^[A-Za-z0-9._-]{1,128}$` に収まるようにする。元ファイル名をそのままBlob pathに入れない。正規化できない場合は、拡張子だけを検証したうえで `input.{ext}` のようなcanonical nameへフォールバックし、元ファイル名はCosmos DBの `input.fileName` にのみ保持する。

## 3. Cosmos DB コンテナー

### 3.1 jobs

Partition key: `/tenantId`  
Unique key: `tenantId + jobId`

```json
{
  "id": "01JZ...",
  "tenantId": "tenant-001",
  "jobId": "01JZ...",
  "userId": "user-001",
  "meetingTitle": "顧客定例会",
  "status": "GENERATING_CHUNK_SUMMARIES",
  "locale": "ja-JP",
  "maxSpeakers": 8,
  "input": {
    "fileName": "meeting.mp3",
    "contentType": "audio/mpeg",
    "fileSizeBytes": 123456789,
    "clientEstimatedDurationSeconds": 4800,
    "rawAudioBlobUri": "https://.../raw-audio/..."
  },
  "outputs": {
    "rawTranscriptBlobUri": "https://.../speech-response.json",
    "normalizedTranscriptBlobUri": "https://.../normalized-transcript.json",
    "minutesJsonBlobUri": "https://.../minutes.v1.json",
    "minutesMarkdownBlobUri": "https://.../minutes.v1.md"
  },
  "progress": {
    "step": "GENERATING_CHUNK_SUMMARIES",
    "percent": 72,
    "message": "議事録の暫定要約を生成しています",
    "updatedAt": "2026-05-29T10:20:00Z"
  },
  "timings": {
    "createdAt": "2026-05-29T10:00:00Z",
    "uploadedAt": "2026-05-29T10:05:00Z",
    "transcriptionStartedAt": "2026-05-29T10:05:10Z",
    "transcriptReadyAt": "2026-05-29T10:11:00Z",
    "minutesReadyAt": null
  },
  "metrics": {
    "speechRetryCount": 0,
    "openaiPromptTokens": 0,
    "openaiCompletionTokens": 0,
    "chunkCount": 0
  },
  "error": null,
  "etag": "..."
}
```

`progress` は全状態で必ず保存する。`CREATED` 直後は `step: "CREATED"`, `percent: 0`, `message: "Job created"` のような安全な初期値をAPI層で設定し、Activityが進むたびに上書きする。

### 3.2 speakerMappings

Partition key: `/tenantId`

```json
{
  "id": "01JZ...:speakerMapping:v1",
  "tenantId": "tenant-001",
  "jobId": "01JZ...",
  "version": 1,
  "speakers": [
    {
      "speakerLabel": "Speaker 0",
      "displayName": "山田さん",
      "representativePhrases": [
        {
          "offsetMilliseconds": 120000,
          "text": "本日のアジェンダは..."
        }
      ]
    }
  ],
  "createdAt": "2026-05-29T10:30:00Z",
  "updatedAt": "2026-05-29T10:30:00Z"
}
```

### 3.3 actionItems

Partition key: `/tenantId`

```json
{
  "id": "01JZ...:action:001",
  "tenantId": "tenant-001",
  "jobId": "01JZ...",
  "task": "次回までにPoC環境を準備する",
  "owner": "山田さん",
  "dueDate": "2026-06-05",
  "status": "open",
  "sourceTimestamp": "00:42:10",
  "createdAt": "2026-05-29T10:35:00Z"
}
```

### 3.4 auditEvents

Partition key: `/tenantId`

```json
{
  "id": "01JZ...:event:0001",
  "tenantId": "tenant-001",
  "jobId": "01JZ...",
  "eventType": "JOB_CREATED",
  "actorUserId": "user-001",
  "occurredAt": "2026-05-29T10:00:00Z",
  "details": {
    "fileSizeBytes": 123456789
  }
}
```

## 4. Job status

正式なスキーマは `specs/job-status.schema.json` を参照。

| status | 説明 | 終了状態 |
|---|---|---:|
| `CREATED` | ジョブ作成済み | No |
| `UPLOADING` | アップロード中 | No |
| `UPLOADED` | アップロード完了 | No |
| `VALIDATING` | 入力検証中 | No |
| `PREPROCESSING` | 前処理中 | No |
| `TRANSCRIBING` | 文字起こし中 | No |
| `TRANSCRIPT_READY` | transcript生成済み | No |
| `GENERATING_CHUNK_SUMMARIES` | チャンク要約中 | No |
| `GENERATING_FINAL_MINUTES` | 最終議事録生成中 | No |
| `REVIEW_REQUIRED` | speaker mapping等の確認待ち | No |
| `DONE` | 完了 | Yes |
| `FAILED` | 失敗 | Yes |
| `CANCELLED` | キャンセル | Yes |

## 5. Normalized transcript

正式なスキーマは `specs/normalized-transcript.schema.json` を参照。

重要な設計方針:

- `speakerLabel` は `Speaker 0` のようにアプリ側で統一する。
- `displayName` は speaker mapping 適用後だけ入れる。
- `offsetMilliseconds` と `durationMilliseconds` は数値で保持する。
- UI用に `startTimeText` は生成してよいが、保存の正は数値。

## 6. Minutes JSON

正式なスキーマは `specs/minutes.schema.json` を参照。

議事録JSONは人間が読むMarkdownの生成元にする。構造化された action items もここから抽出して Cosmos DB に保存する。

必須要素:

- jobId
- tenantId
- title
- summary
- topics
- decisions
- actionItems
- openQuestions
- risks
- generatedAt

根拠timestampはトップレベル必須ではなく、`topics[].evidenceTimestamps` と各 `decisions` / `actionItems` / `openQuestions` / `risks` の `sourceTimestamps` に保持する。

## 7. データ保持期間

初期値:

| データ | 既定保持期間 | 備考 |
|---|---:|---|
| raw audio | 30日 | 顧客要件で短縮可能 |
| raw transcript | 180日 | 再生成用 |
| normalized transcript | 180日 | 再生成用 |
| minutes | 1年 | 業務要件に合わせる |
| auditEvents | 1年 | 監査要件に合わせる |
| Application Insights logs | 30〜90日 | コストに合わせる |

## 8. インデックス設計

Cosmos DB jobs のクエリ:

- tenantId + userId + createdAt desc
- tenantId + status
- tenantId + jobId

Action items のクエリ:

- tenantId + owner + status
- tenantId + dueDate
- tenantId + jobId

## 9. 将来のAzure AI Search連携

過去議事録検索が必要になったら、以下をAzure AI Searchにインデックスする。

- meetingTitle
- meetingDate
- participant display names
- topic title
- topic discussion
- decisions
- actionItems
- transcript chunks
- embeddings

検索は、キーワード検索とベクトル検索を同一リクエストで行うハイブリッド検索を使う。
