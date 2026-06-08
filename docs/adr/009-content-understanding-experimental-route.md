# ADR-009: Content Understanding実験経路の採否と評価方針

## Status

Accepted

## Context

Minutes Studio の本線は、全体音声を Azure Speech in Foundry Tools Fast Transcription に1回投入し、diarization を有効にして speaker ID と timestamp 付きの normalized transcript を作る方式である。この方式は、音声チャンク並列STTより speaker label の一貫性を保ちやすい。

一方、Azure Content Understanding in Foundry Tools は video/audio の解析結果として `transcriptPhrases`、key frames、camera shots、visual fields、markdown などを返せる。MP4を扱うデモでは、映像由来の補足情報をUIに表示できる価値がある。ただし、現行のAI処理ルールでは「transcriptにない事実を議事録へ追加しない」「決定事項・担当者・期限を推測しない」「根拠timestampを残す」ことを必須にしている。

## Decision

Content Understanding は、現時点では **実験経路** として残す。標準経路を置き換えない。

| 論点 | 決定 |
|---|---|
| 文字起こし本線 | 引き続き Fast Transcription + diarization を標準経路にする |
| CU経路 | `processingRoute=contentUnderstanding` として明示選択できる実験経路にする |
| 映像情報 | Phase 1では議事録本文へ混ぜず、visual context artifactとして保存しUIの「映像メモ」で表示する |
| 議事録生成 | CU `transcriptPhrases` を normalized transcript へ変換し、既存のOpenAI minutes generatorへ渡す |
| CU custom fields / markdown | 現行minutes schemaの直接生成元にはしない |
| 採用判定 | 長尺/大容量E2E、Fast TranscriptionとのA/B、コスト、失敗率、データガバナンスを確認後に再評価する |

## Current gap analysis

| 現行要件 | CU出力との対応 | 判断 |
|---|---|---|
| speaker label 一貫性 | `transcriptPhrases` にspeaker情報が含まれる場合は変換可能 | Fast TranscriptionとのA/Bが必要 |
| timestamp evidence | phrase timestamp は normalized transcript へ変換可能 | 精度・粒度の比較が必要 |
| minutes schema | CU fields/markdown は `minutes.schema.json` と一致しない | 直接保存しない |
| visual evidence | key frames/camera shots/fields は文字起こし由来ではない | Phase 1では議事録本文の根拠にしない |
| 120分MP4 | CU video URL参照Analyze APIは2時間境界に近い | 長尺E2Eで失敗率と処理時間を測る |
| 4GB級動画 | URL参照Analyze APIの上限内だが、upload/解析時間/コストが大きい | 顧客デモ前に代表ファイルで検証する |
| 機密ログ禁止 | CU operation URL、content URL、SAS、解析本文をログに出さない | 既存のredaction方針を維持する |

長尺E2E評価では、Durable Functions側のCU operation polling予算が入力上限時間と同じ程度だと、CU解析能力ではなくアプリ側timeoutで失敗判定になる。120分近傍の評価前に、polling回数/間隔/timeoutを評価用に明示し、失敗理由を `TimedOut` とCU operation failureに分けて記録する。

## E2E evaluation conclusion

CU経路は、短いMP4で「CU Analyze -> `transcriptPhrases` 正規化 -> 既存minutes generator -> visual context表示」まで成立している。これは **デモ用の選択肢として有効** である。

ただし、CU custom field extraction だけで現行minutes JSONを直接生成する方式は採用しない。理由は、現行minutes schemaが決定事項、ToDo、未決事項、リスク、根拠timestamp、null owner/dueDateなどの厳密な構造を要求しており、CU fields/markdownをそのまま保存すると検証・根拠・推測禁止ルールが崩れるためである。

## A/B test plan

CUを標準経路へ昇格する前に、同じ入力で次を比較する。

| 観点 | 比較対象 |
|---|---|
| speaker labels | Fast Transcription diarization vs CU `transcriptPhrases` speaker |
| speaker label safety | CU speaker値が実名や個人識別情報にならないこと、標準経路の `Speaker N` 形式との差 |
| timestamp粒度 | phrase start/end と議事録 evidence timestamp |
| phrase segmentation | 発話分割の自然さ、短すぎ/長すぎの頻度 |
| transcript欠落 | 人手確認で重要発話が欠けていないか |
| minutes品質 | 決定事項/ToDo/未決事項/リスクの抜け・誤追加 |
| latency | upload完了から transcript ready / minutes ready まで |
| cost | CU解析、OpenAI minutes generation、Storage/Functions実行時間 |
| failure mode | timeout、429/5xx、operation失敗、schema validation失敗 |

## Consequences

- 標準経路の話者分離品質を守りながら、MP4デモで映像補足を見せられる。
- CU経路は明示選択に限定されるため、通常の音声処理を不安定化させにくい。
- visual contextはartifactとして保存されるが、minutes本文の根拠には使わないため、ユーザーは映像メモを人間判断で確認する必要がある。
- 将来、映像情報をminutes本文に使う場合は、`minutes.schema.json` に visual evidence を追加し、プロンプト・検証・UI・監査ログのADRを別途作る。
- CU採否は、短いsmoke成功だけでは決めない。長尺/大容量のE2EとA/B評価が必要である。

## Re-evaluation triggers

次のいずれかに該当した場合、このADRを見直す。

1. CU `transcriptPhrases` がFast Transcriptionより安定して高品質なspeaker/timestampを示した。
2. CUがprivate Storage / managed identity fetchなど、閉域構成に適した入力方式を公式に満たした。
3. 映像由来情報を議事録本文へ入れる顧客要件が発生した。
4. CU経路の長尺/大容量E2Eでtimeoutまたはコストが許容できないことが分かった。
5. `minutes.schema.json` またはAI処理ルールを変更する必要が出た。

## Alternatives considered

1. **CUを標準経路へ昇格する。** MP4映像情報を扱いやすいが、speaker label品質とminutes根拠ルールの検証が不足している。
2. **CUをsidecar専用にする。** 標準transcriptを維持しつつ映像メモだけを追加できる。将来の安定案だが、現行では実験経路としてCU transcriptも比較できるよう残す。
3. **CUを採用しない。** 標準経路は単純になるが、MP4デモで映像補足を示せない。
