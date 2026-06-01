# Task 03: Implement Durable Functions workflow skeleton

Durable Functions の workflow 骨格を実装してください。

## 参照する仕様

- `docs/05-workflow-spec.md`
- `docs/04-data-model.md`
- `AGENTS.md`

## 実装対象

- `MeetingMinutesOrchestrator`
- `LoadJobActivity`
- `ValidateInputActivity`
- `CreateReadSasActivity`
- `TranscribeAudioActivity` は stub で可
- `NormalizeTranscriptActivity` は sample response で可
- `BuildTranscriptChunksActivity`
- `GenerateChunkSummaryActivity` は stub で可
- `GenerateFinalMinutesActivity` は stub で可
- `RenderMarkdownActivity`
- `CompleteJobActivity`
- `FailJobActivity`

## 必須条件

- Orchestrator内でI/Oしない。
- custom status を更新する。
- Activityは冪等にする。
- 失敗時に `FAILED` へ遷移する。
- サンプルデータで `DONE` まで進むテストを用意する。

## 注意

- まだ実Azure接続は不要です。
- Speech/OpenAI連携は次タスクで実装します。
