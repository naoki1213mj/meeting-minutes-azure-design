# ADR-007: transcript全文による議事録生成とchunk fallback

## Status

Accepted

## Context

Minutes Studio は最大120分程度の録音済み会議を対象にする。文字起こし経路は、すでに音声全体を Azure Speech in Foundry Tools Fast Transcription に1回投入し、diarization を有効にしている。この方式は会議全体で speaker label の一貫性を保ちやすく、音声をチャンクごとに文字起こしした場合に発生する「チャンクごとに `Speaker 1` の人物が変わる」問題を避けられる。

一方、従来の議事録生成は normalized transcript をチャンク分割し、chunk summary を作り、それらを最終統合していた。50分m4aのlive E2E計測では、全体224.6秒のうち主な内訳は次のとおりだった。

| Activity | Duration |
|---|---:|
| TranscribeAudioActivity | 97.18s |
| GenerateChunkSummaryActivity | 6 chunks, 51.63s total |
| GenerateFinalMinutesActivity | 76.79s |

想定上限が120分であれば、通常の normalized transcript はGPT-5.4系deploymentの大きなcontextに収まる見込みが高い。chunk summary方式は長大入力への安全策としては有効だが、本線にするとLLM呼び出し回数と統合処理が増え、文脈や情報が中間要約で落ちる可能性もある。

## Decision

本線は次の処理方式にする。

```text
音声全体
-> Fast Transcription 1回 + diarization
-> normalized transcript
-> transcript全文を使ったStructured outputs議事録生成
-> minutes.schema.jsonで保存前検証
-> Markdown rendering
```

chunk summary方式は削除せず、本線ではなく自動fallbackとして残す。direct生成で出力切れ、token/context制約、JSON破損、schema repair失敗などの回復可能な制約に当たった場合だけfallbackする。

UIでは議事録生成モデルを選択できるようにする。

| UI option | API value | 想定deployment | 用途 |
|---|---|---|---|
| 高速 | `fast` | GPT-5.4 mini | 既定。待ち時間を短縮 |
| 高品質 | `quality` | GPT-5.4 | 重要会議で品質を優先 |

Backendは固定された選択肢だけを設定済みdeploymentへマッピングする。クライアントから任意deployment名を受け取らない。

音声長は120分までbest effortで受け付け、120分超は拒否する。120分はFast Transcription diarizationの2時間境界に近いため、UIとdocsではbest effort上限であることを明示する。

## Consequences

- 音声をチャンク文字起こししないため、speaker label の一貫性を守りやすい。
- 通常経路からchunk summary呼び出しが消えるため、E2E短縮が期待できる。
- transcript全文を直接根拠にするため、中間要約による情報落ちを減らせる。
- 長い/密度の高いtranscriptでdirect生成が制約に当たる場合でも、chunk fallbackで回復できる。
- `BuildTranscriptChunksActivity` と `GenerateChunkSummaryActivity` はfallback・互換用に残すが、通常のOrchestrator本線では呼ばない。
- telemetryではdirect/fallbackを区別する。ただしtranscript全文、prompt全文、minutes全文、SAS URL、token、secretはログに出さない。

## Alternatives considered

1. **chunk summary方式を本線のまま維持する。** 小さいcontext modelには堅牢だが、120分上限のMVPでは遅延と複雑さが大きい。
2. **音声チャンク並列文字起こしを行う。** 文字起こし時間は短縮できるが、チャンク間のspeaker label整合が崩れるため、話者分離品質を優先する本線にはしない。
3. **fallbackなしのdirect生成にする。** 最も単純だが、出力切れやtoken制約がそのままジョブ失敗になる。自動fallbackを残す方が安全。
