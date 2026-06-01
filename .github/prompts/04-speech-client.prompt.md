# Task 04: Implement Azure Speech Fast Transcription client

Azure Speech in Foundry Tools Fast Transcription のクライアントを実装してください。

## 参照する仕様

- `docs/05-workflow-spec.md` の `TranscribeAudioActivity`
- `docs/10-official-references.md`
- `AGENTS.md`

## 実装対象

1. SpeechTranscriptionClient interface
2. FastTranscriptionClient 実装
3. retry policy
4. error normalization
5. raw response のBlob保存連携

## リクエスト要件

- endpoint: `/speechtotext/transcriptions:transcribe?api-version=2025-10-15`
- 本番経路では `definition.audioUrl` を使う。
- inline `audio` は小さい開発・検証用に限定し、80分音声の本番経路では実装しない。
- `locales` は既定で `["ja-JP"]`。
- `diarization` は `{ "enabled": true, "maxSpeakers": 8 }`。
- `channels` は指定しない。
- Microsoft Entra ID の bearer token を優先する。
- API key fallback は設定がある場合だけ許可する。
- read SAS TTL は、Speechサービスのfetchとretryが終わるまで切れない設定にする。

## Retry

- retry: 429, 500, 502, 503, 504, network errors
- no retry: 400, 401, 422, other 4xx
- backoff: 2, 4, 8, 16, 32秒。テストでは待たないようにsleepを注入可能にする。

## テスト

- 正しいdefinitionが生成され、`audioUrl` が含まれること。
- `channels` が含まれないこと。
- retry対象エラーで再試行されること。
- 4xxで再試行しないこと。
- SAS URL全文をログに出さないこと。
