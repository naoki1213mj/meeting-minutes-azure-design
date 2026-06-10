# ADR-010: 長尺音声向けBatch Transcription fallback

## Status

Accepted

## Context

標準経路は Azure Speech in Foundry Tools Fast Transcription を使い、音声全体を1回だけ文字起こしする。diarizationを有効にするため、Fast Transcriptionの実質上限は500MB未満かつ2時間未満である。

一方、ユーザーがアップロードするm4a/mp4はFunctions内で16kHz mono FLACへ正規化するため、2時間以内なら抽出後音声が500MBを超える可能性は低い。実際の壁はサイズよりもdiarization有効時の2時間制限である。

音声チャンク分割とoverlapによるSTTは、チャンク間でspeaker labelが一致しない可能性が高く、Minutes Studioが重視する話者分離品質と衝突する。

## Decision

標準経路でFast Transcription上限を超える長尺音声は、Batch Transcriptionへ自動fallbackする。

| 条件 | 処理 |
|---|---|
| 500MB未満かつ2時間未満 | Fast Transcription |
| 1GB未満かつ4時間未満 | Batch Transcription fallback |
| 1GB以上または4時間以上 | 拒否。将来の分割モード候補 |

Batch fallbackはユーザーが別モードを選択するのではなく、標準経路内で自動判定する。UIでは現在の文字起こしエンジンを表示し、Batch中は完了まで時間がかかる可能性を明示する。

Batch REST APIは `/speechtotext/transcriptions:submit?api-version=2024-11-15` を使う。diarizationは `properties.diarization.enabled=true` と `maxSpeakers` で有効化し、`channels` は指定しない。結果取得時は `kind: "Transcription"` のファイルだけを正規化し、Batch結果の `source` に含まれ得る入力SAS URLはartifact保存前にredactする。

Batchは開始待ちと処理で最大24時間かかる可能性があるため、Batchへ渡す入力Blobのread SASはFast/CU向けの短TTLとは分け、既定25時間のBatch専用TTLで発行する。

## Consequences

- 2時間超〜4時間未満の会議を、話者分離品質を比較的保ったまま処理できる可能性がある。
- Fastより遅く、Speech側のキューにより数十分〜数時間かかる可能性がある。
- Batch結果形式はFastと異なるため、専用normalizerが必要になる。
- Batchも4時間/1GBを超える入力は扱えない。将来は話者精度低下を明示した分割STT縮退モードを検討する。
- App内ガイドでFast/Batch/CUの違いとAzure構成を説明し、デモ中に別資料へ戻らなくてもよいようにする。

## Alternatives considered

1. **現行どおり拒否。** 品質は最も安全だが、2時間超の会議に対応できない。
2. **音声チャンク + overlap。** 上限は超えられるがspeaker labelの一貫性を保証できない。
3. **低ビットレート再圧縮。** サイズには効くが、2時間制限には効かず、ASR/diarization品質も落ちる。
4. **Batch fallback。** 長尺向きで、音声全体を1つのjobとして扱えるため第一候補にする。
