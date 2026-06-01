# 05. ワークフロー詳細仕様

確認日: 2026-06-01

## 1. Orchestrator

関数名案: `MeetingMinutesOrchestrator`

入力:

```json
{
  "tenantId": "tenant-001",
  "jobId": "01JZ...",
  "userId": "user-001"
}
```

出力:

```json
{
  "jobId": "01JZ...",
  "status": "DONE",
  "minutesJsonBlobUri": "https://...",
  "minutesMarkdownBlobUri": "https://..."
}
```

2026-06-01時点のdev MVPは Azure Functions Premium EP1 / Python 3.13 で稼働し、Azure上のDurable Functionsは v1 `function.json` wrappersで登録する。`function_app.py` はローカル・テスト用で、デプロイパッケージから除外する。

## 2. Activity一覧

| Activity | 入力 | 出力 | Retry | dev MVP状態 |
|---|---|---|---|---|
| `LoadJobActivity` | tenantId, jobId | job | あり | 実装済み |
| `ValidateInputActivity` | job | validationResult | なし | 実装済み |
| `CreateReadSasActivity` | job | readSasUrl | あり | 実装済み。m4aの場合は16kHz mono FLACへ前処理してからread SASを返す |
| `TranscribeAudioActivity` | job, readSasUrl | rawTranscriptBlobUri | あり | live E2E済み |
| `NormalizeTranscriptActivity` | rawTranscriptBlobUri | normalizedTranscriptBlobUri | あり | live E2E済み |
| `BuildTranscriptChunksActivity` | normalizedTranscriptBlobUri | chunk descriptors | あり | live E2E済み |
| `GenerateChunkSummaryActivity` | chunk descriptor | chunk summary blob | あり | `task_all` fan-outでlive E2E済み |
| `GenerateFinalMinutesActivity` | chunk summaries | minutes JSON blob | あり | live E2E済み |
| `RenderMarkdownActivity` | minutes JSON blob | markdown blob | あり | live E2E済み |
| `PersistActionItemsActivity` | minutes JSON blob | action items count | あり | Phase 2で拡充 |
| `CompleteJobActivity` | job outputs | job | あり | 実装済み |
| `FailJobActivity` | error | job | なし | 実装済み |

## 3. Orchestrator疑似コード

```python
def orchestrator(context):
    input = context.get_input()
    tenant_id = input["tenantId"]
    job_id = input["jobId"]

    try:
        context.set_custom_status({"step": "LOADING_JOB", "percent": 1})
        job = yield context.call_activity("LoadJobActivity", input)

        context.set_custom_status({"step": "VALIDATING", "percent": 5})
        validation = yield context.call_activity("ValidateInputActivity", job)

        context.set_custom_status({"step": "CREATING_AUDIO_READ_URL", "percent": 10})
        read_sas_url = yield context.call_activity("CreateReadSasActivity", job)

        context.set_custom_status({"step": "TRANSCRIBING", "percent": 15})
        raw_transcript_uri = yield context.call_activity_with_retry(
            "TranscribeAudioActivity",
            retry_options_for_speech,
            {"job": job, "audioUrl": read_sas_url},
        )

        context.set_custom_status({"step": "NORMALIZING_TRANSCRIPT", "percent": 55})
        normalized_uri = yield context.call_activity("NormalizeTranscriptActivity", raw_transcript_uri)

        context.set_custom_status({"step": "BUILDING_CHUNKS", "percent": 60})
        chunks = yield context.call_activity("BuildTranscriptChunksActivity", normalized_uri)

        context.set_custom_status({"step": "GENERATING_CHUNK_SUMMARIES", "percent": 65})
        tasks = [context.call_activity_with_retry("GenerateChunkSummaryActivity", retry_options_for_openai, c) for c in chunks]
        chunk_summary_uris = yield context.task_all(tasks)

        context.set_custom_status({"step": "GENERATING_FINAL_MINUTES", "percent": 90})
        minutes_uri = yield context.call_activity_with_retry(
            "GenerateFinalMinutesActivity",
            retry_options_for_openai,
            {"job": job, "chunkSummaryUris": chunk_summary_uris},
        )

        markdown_uri = yield context.call_activity("RenderMarkdownActivity", minutes_uri)
        yield context.call_activity("PersistActionItemsActivity", minutes_uri)

        context.set_custom_status({"step": "DONE", "percent": 100})
        return yield context.call_activity("CompleteJobActivity", {
            "jobId": job_id,
            "minutesJsonBlobUri": minutes_uri,
            "minutesMarkdownBlobUri": markdown_uri,
        })
    except Exception as e:
        return yield context.call_activity("FailJobActivity", {
            "jobId": job_id,
            "error": serialize_error(e),
        })
```

`CreateReadSasActivity` は名前上はSAS発行だが、dev MVPではm4a互換性対応もここで行う。入力音声がm4aの場合、Cosmosのprogressを `PREPROCESSING` にし、`imageio-ffmpeg` のffmpegで16kHz mono FLACへ変換し、audio container内の `preprocessed/{tenantId}/{jobId}/input.flac` に保存してから、そのBlobのread SASを返す。m4a以外は元のraw audio Blobのread SASを返す。

Orchestrator内でネットワークI/O、Blob/Cosmos I/O、現在時刻取得などの非決定的処理を直接行わない。I/Oと副作用はActivityへ閉じ込める。

## 4. ValidateInputActivity

### 入力検証ルール

| 項目 | 既定値 | 動作 |
|---|---:|---|
| 通常サイズ上限 | 300MB | 超過時は既定でエラー |
| ハードサイズ上限 | 500MB | 超過時は必ずエラー |
| diarization有効時の音声長 | 2時間未満 | 超過時は必ずエラー |
| locale | `ja-JP` | 未指定時に設定 |
| maxSpeakers | 8 | 未指定時に設定 |

### 音声長チェック

Phase 1では次の順序で扱う。

1. ブラウザで取得できた `clientEstimatedDurationSeconds` を参考値として保存する。
2. 2時間以上ならアップロード前またはジョブ作成時に警告・拒否する。
3. バックエンドで厳密な音声長が必要になったら、Phase 2で ffprobe を使う `ProbeAudioActivity` を追加する。
4. Speech API 側で2時間超過エラーになった場合は、`AUDIO_TOO_LONG_FOR_DIARIZATION` に正規化する。

## 5. TranscribeAudioActivity

### Fast Transcription request

REST APIの形式は公式ドキュメントの `transcriptions:transcribe` を基準にする。本番経路では、長い音声向けに推奨される `audioUrl` 方式を使い、inline `audio` は小さい開発・検証用に限定する。

```bash
curl --location "https://{speechResourceName}.cognitiveservices.azure.com/speechtotext/transcriptions:transcribe?api-version=2025-10-15" \
  --header "Authorization: Bearer {accessToken}" \
  --header "Content-Type: multipart/form-data" \
  --form 'definition={
    "audioUrl": "<user-delegation-sas-url>",
    "locales": ["ja-JP"],
    "diarization": {"enabled": true, "maxSpeakers": 8}
  }'
```

### 実装注意

- 長い音声では `audioUrl` を使う。80分音声の本番経路では inline `audio` を使わない。
- `channels` は指定しない。diarization 有効時にステレオの `[0,1]` 指定は避ける。
- 429, 500, 502, 503, 504, network errors はリトライする。
- 400, 401, 422, その他4xxはリトライしない。
- `audioUrl` のSAS TTLは、Speechサービスの取得時間とリトライ時間を含めて切れない長さにする。初期値は90分。
- raw response は必ずBlobに保存する。
- 音声本文、SAS URL全文、Authorization header はログに出さない。

## 6. NormalizeTranscriptActivity

### 入力

Speech API raw response。

### 出力

`specs/normalized-transcript.schema.json` に準拠するJSON。

### 変換ルール

- `phrase.speaker` が存在する場合は `Speaker {speaker}` に変換する。
- speakerがない場合は `Unknown`。
- offset/duration はミリ秒で保存する。
- UI表示用に `startTimeText` を `HH:MM:SS` で生成する。
- transcript全体の `durationMilliseconds` を保存する。

## 7. BuildTranscriptChunksActivity

### 分割方針

- 5〜10分相当を目安にする。
- phraseの途中では分割しない。
- topic境界を完全に推定しようとしない。
- chunkごとに前後30秒程度の overlap を任意で持たせてもよい。
- overlap を入れた場合は final merge で重複を除去する。
- chunk descriptorとchunk inputは deterministic なBlob pathに保存し、再実行時に同じ場所へ上書きできるようにする。

### 出力例

```json
[
  {
    "chunkIndex": 0,
    "startOffsetMilliseconds": 0,
    "endOffsetMilliseconds": 600000,
    "blobUri": "https://.../chunk-0-input.json"
  }
]
```

## 8. GenerateChunkSummaryActivity

### 出力

```json
{
  "chunkIndex": 0,
  "summary": "...",
  "topics": [
    {
      "title": "...",
      "discussion": "...",
      "decisions": ["..."],
      "openQuestions": ["..."],
      "actionItems": [
        {
          "task": "...",
          "owner": "Speaker 0",
          "dueDate": null,
          "sourceTimestamp": "00:12:34"
        }
      ],
      "evidenceTimestamps": ["00:12:34"]
    }
  ]
}
```

### 並列化と性能制御

- Orchestratorは `context.task_all(tasks)` でchunk summaryをfan-out/fan-inする。
- 同時実行数は設定値で制御できるようにし、Azure OpenAI 429やTPM消費を見て下げられるようにする。
- dev MVPでは `gpt-5.4-mini` / `gpt-5.4` をGlobalStandard capacity 100に増強済み。capacity 1および10ではlive smokeのfinal mergeで429が発生したため、capacity増強とバックオフが必要。
- final mergeは長尺音声でJSONが途中切れしないよう `max_completion_tokens=32768` と `reasoning_effort=low` を設定する。`finish_reason=length` は本文をログに出さずtruncationとして扱う。
- chunk summary全文やtranscript全文をログに出さない。ログはchunkIndex、duration、retryCount、tokenUsageなどに限定する。

## 9. GenerateFinalMinutesActivity

### 入力

全chunk summary。

### 処理

- 重複する決定事項を統合する。
- action items を統合する。
- 期限が明示されない場合は `dueDate: null` にする。
- 推測で担当者を埋めない。明示されない場合は `owner: null`。
- 根拠 timestamp を保持する。
- LLM出力は `minutes.structured-output.schema.json` で制御する。
- アプリ側で `jobId`, `tenantId`, `generatedAt`, `model` を付与する。
- 保存前に `minutes.schema.json` で検証する。

## 10. リトライ方針

| 対象 | リトライ対象 | 回数 | バックオフ |
|---|---|---:|---|
| Speech | 429, 500, 502, 503, 504, network | 最大5回 | 2,4,8,16,32秒 + jitter |
| Azure OpenAI | 429, 500, 502, 503, 504, network | 最大5回 | 2,4,8,16,32秒 + jitter |
| Blob | 408, 429, 5xx, network | SDK既定 + 明示ログ | SDK既定 |
| Cosmos DB | 429, 5xx | SDK既定 | SDK既定 |

429が継続する場合は、単純に再試行を増やすのではなく、chunk summary並列度、UIポーリング間隔、モデルdeployment capacity、TPM/RPM quotaを見直す。

## 11. 失敗時の状態遷移

- Activityで復旧不能エラーが出たら `FAILED` にする。
- `error.code`, `error.message`, `error.details`, `correlationId` を保存する。
- ユーザー向けメッセージは技術詳細を出しすぎない。
- 管理者向けには詳細を表示できるようにする。
- 失敗時もSAS URL全文、音声本文、transcript全文、minutes全文、token/keyは保存・表示・ログ出力しない。

## 12. キャンセル

Phase 1ではUI上のキャンセルは任意。実装する場合:

- `POST /api/jobs/{jobId}:cancel` を追加する。
- Durable orchestration を terminate する。
- Blobは保持期間に従って削除する。

## 13. 現在の確認実績

- 短い日本語TTS音声で upload -> Durable workflow -> Fast Transcription + diarization -> normalized transcript -> chunk summary fan-out -> final merge -> Markdown rendering -> `DONE` を確認済み。
- `GET /api/jobs/{jobId}/transcript` と `GET /api/jobs/{jobId}/minutes` で成果物取得を確認済み。
- chunk input / chunk summary / final minutes / markdown artifacts がBlobに保存されることを確認済み。
- Application InsightsスキャンでSAS/query/audio/upload URLs、API keys、access tokens、client secrets、Bearer tokensは検出されず、Azure SDK Authorization tracesはredact済みだった。
