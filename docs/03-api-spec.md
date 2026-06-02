# 03. API仕様

確認日: 2026-06-01

正式なOpenAPI定義は `specs/openapi.yaml` を参照する。この文書は実装意図とdev MVPの実装状況を説明する。

## 1. 共通方針

- APIはJSONを返す。
- 認証は Microsoft Entra ID を前提にする。
- 2026-06-01時点のdev MVPは `MEETING_MINUTES_AUTH_MODE=demo` で固定の `demo-tenant` / `demo-user` を使う。Azure環境では `x-dev-tenant-id` / `x-dev-user-id` を信用しないが、これは本番認証ではない。
- 本番・実データ・広範な共有利用の前に Microsoft Entra ID / Easy Auth を強制し、token claims から tenantId / userId を取得する。
- APIは長時間処理を待たない。
- `POST /api/jobs` は `201 Created` で uploadUrl を返す。`POST /api/jobs/{jobId}/upload-complete` は `202 Accepted` で非同期workflow開始を返す。
- 音声本文、transcript全文、議事録全文は通常ログに出さない。
- すべてのレスポンスに correlation ID を紐づける。リクエストに `x-correlation-id` があれば検証後に引き継ぎ、なければAPI入口で生成してエラーレスポンス、ログ、Cosmos DBの失敗情報で同じ値を使う。
- OpenAPIの `JobStatus` は `specs/job-status.schema.json` を参照する。OpenAPI内の `JobStatusEnum` はツール互換性のためのローカル定義で、`specs/job-status.schema.json#/properties/status/enum` とCIで一致を検査する。
- 受理する拡張子は `.mp3`, `.wav`, `.m4a`, `.mp4`, `.ogg`, `.webm`, `.flac`。
- m4a/mp4は `audio/mp4`, `audio/m4a`, `audio/x-m4a`, `audio/aac`, `video/mp4`, `application/mp4`, または対応拡張子 + `application/octet-stream` を受け付け、Backendで音声トラックを16kHz mono FLACへ前処理してから文字起こしする。

## 2. エンドポイント一覧

| Method | Path | 用途 | dev MVP状態 |
|---|---|---|---|
| POST | `/api/jobs` | ジョブ作成とアップロードURL発行 | 実装・live smoke済み |
| POST | `/api/jobs/{jobId}/upload-complete` | アップロード完了通知とworkflow開始 | 実装・live smoke済み |
| GET | `/api/jobs/{jobId}` | ジョブ状態取得 | 実装・live smoke済み |
| GET | `/api/jobs/{jobId}/transcript` | 正規化済みtranscript取得 | 実装・live E2E済み |
| GET | `/api/jobs/{jobId}/minutes` | 議事録取得 | 実装・live E2E済み |
| PUT | `/api/jobs/{jobId}/speaker-mapping` | speaker ID と表示名の紐付け更新 | Phase 2以降 |
| POST | `/api/jobs/{jobId}/minutes:regenerate` | speaker mapping 反映などによる議事録再生成 | Phase 2以降 |
| POST | `/api/jobs/{jobId}:retry` | 失敗ジョブの再実行 | Phase 2以降 |
| GET | `/api/jobs` | ジョブ一覧 | Phase 2以降 |

## 3. POST /api/jobs

### Request

```json
{
  "fileName": "meeting.mp3",
  "contentType": "audio/mpeg",
  "fileSizeBytes": 123456789,
  "clientEstimatedDurationSeconds": 4800,
  "meetingTitle": "顧客定例会",
  "locale": "ja-JP",
  "maxSpeakers": 8
}
```

### Response 201

```json
{
  "jobId": "01JZ...",
  "status": "CREATED",
  "blobName": "raw-audio/tenant-001/01JZ.../meeting.mp3",
  "uploadUrl": "https://...sas...",
  "uploadExpiresAt": "2026-05-29T10:15:00Z",
  "constraints": {
    "normalMaxFileSizeBytes": 314572800,
    "hardMaxFileSizeBytes": 524288000,
    "maxDurationSecondsWithDiarization": 7200
  }
}
```

### バリデーション

- `fileName` は必須。
- `fileSizeBytes` は必須。
- 通常は `fileSizeBytes < 300MB` を推奨。
- 300MB以上は設定により許可する。既定ではエラーにする。
- `contentType` と拡張子の組み合わせを検証する。`application/octet-stream` はサポート対象拡張子に限って許可する。
- APIが受理する形式とFast TranscriptionでE2E確認済みの形式は分けて扱う。2026-06-02時点のlive E2E確認済みは短いWAVとm4a→FLAC前処理経路。
- `locale` 未指定時は `ja-JP`。
- `maxSpeakers` 未指定時は8。上限はアプリ設定で制御する。

## 4. POST /api/jobs/{jobId}/upload-complete

### Request

```json
{
  "uploadedSizeBytes": 123456789,
  "clientSha256": "optional"
}
```

### Response 202

```json
{
  "jobId": "01JZ...",
  "status": "UPLOADED",
  "orchestrationInstanceId": "01JZ...",
  "statusUrl": "/api/jobs/01JZ..."
}
```

### 処理

- Blob存在確認。
- Blobサイズ確認。
- job所有者確認。
- 状態を `UPLOADED` に更新。
- Durable orchestration を jobId を instanceId として開始。
- 既に開始済みなら既存instanceを返す。

## 5. GET /api/jobs/{jobId}

### Response 200

```json
{
  "jobId": "01JZ...",
  "tenantId": "tenant-001",
  "status": "GENERATING_CHUNK_SUMMARIES",
  "progress": {
    "step": "GENERATING_CHUNK_SUMMARIES",
    "percent": 72,
    "message": "議事録の暫定要約を生成しています",
    "updatedAt": "2026-05-29T10:20:00Z"
  },
  "timings": {
    "uploadedAt": "2026-05-29T10:10:00Z",
    "transcriptionStartedAt": "2026-05-29T10:10:30Z",
    "transcriptReadyAt": "2026-05-29T10:15:30Z"
  },
  "outputs": {
    "transcriptReady": true,
    "minutesReady": false,
    "rawTranscriptBlobUri": "https://.../speech-response.json",
    "normalizedTranscriptBlobUri": "https://.../normalized-transcript.json",
    "minutesJsonBlobUri": null,
    "minutesMarkdownBlobUri": null
  },
  "error": null,
  "createdAt": "2026-05-29T10:00:00Z",
  "updatedAt": "2026-05-29T10:20:00Z"
}
```

## 6. GET /api/jobs/{jobId}/transcript

### Response 200

`specs/normalized-transcript.schema.json` に準拠する。dev MVPのlive E2Eで取得済み。

## 7. GET /api/jobs/{jobId}/minutes

### Response 200

`specs/minutes.schema.json` に準拠する。OpenAPI上は `format=json|markdown` を定義している。dev MVPのlive E2EでJSON/Markdown成果物の生成と取得を確認済み。

## 8. PUT /api/jobs/{jobId}/speaker-mapping

### Request

```json
{
  "speakers": [
    {
      "speakerLabel": "Speaker 0",
      "displayName": "山田さん"
    },
    {
      "speakerLabel": "Speaker 1",
      "displayName": "佐藤さん"
    }
  ]
}
```

### Response 200

```json
{
  "jobId": "01JZ...",
  "speakerMappingVersion": 2,
  "updatedAt": "2026-05-29T10:30:00Z"
}
```

## 9. POST /api/jobs/{jobId}/minutes:regenerate

### Request

```json
{
  "reason": "speaker_mapping_updated",
  "preserveHumanEdits": true
}
```

### Response 202

```json
{
  "jobId": "01JZ...",
  "status": "GENERATING_CHUNK_SUMMARIES"
}
```

## 10. エラー形式

`error.code`, `error.message`, `error.correlationId` は必須。`details` は内部ログには詳細に残し、APIレスポンスではユーザーに必要な最小限の情報だけにする。

```json
{
  "error": {
    "code": "AUDIO_TOO_LARGE",
    "message": "通常上限の300MBを超えています。音声を圧縮して再アップロードしてください。",
    "details": {
      "fileSizeBytes": 420000000,
      "normalMaxFileSizeBytes": 314572800
    },
    "correlationId": "..."
  }
}
```

## 11. エラーコード

| code | HTTP | 説明 |
|---|---:|---|
| `AUTH_REQUIRED` | 401 | 認証が必要、または認証情報が不足 |
| `FORBIDDEN` | 403 | 認可されていない操作 |
| `INVALID_REQUEST` | 400 | 入力JSONが不正 |
| `UNSUPPORTED_AUDIO_FORMAT` | 400 | 対応外の拡張子またはMIME |
| `AUDIO_TOO_LARGE` | 400 | 通常上限を超過 |
| `AUDIO_EXCEEDS_HARD_LIMIT` | 400 | Fast Transcriptionの上限を超過 |
| `AUDIO_TOO_LONG_FOR_DIARIZATION` | 400 | 2時間以上 |
| `JOB_NOT_FOUND` | 404 | jobIdが存在しない |
| `JOB_ALREADY_RUNNING` | 409 | 既に実行中 |
| `SPEECH_RATE_LIMITED` | 429 | Speech API側のレート制限 |
| `TRANSCRIPTION_FAILED` | 502 | Speech API失敗 |
| `MINUTES_GENERATION_FAILED` | 502 | 議事録生成失敗 |
| `INTERNAL_ERROR` | 500 | 想定外エラー |
