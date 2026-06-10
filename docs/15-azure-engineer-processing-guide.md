# 15. Azureエンジニア向け: 処理方式と運用ポイント

確認日: 2026-06-10

## 1. この資料の対象

この資料は、Azureの基本的なサービスや認証方式を理解しているエンジニアが、Minutes Studio の処理方式、主要リソース、運用上の注意点を短時間で把握するための説明です。詳細なAPI仕様や実装仕様は、各詳細ドキュメントを参照してください。

## 2. 処理フロー概要

```text
Browser
  -> App Service / Express access-key gate
  -> Functions API
  -> User Delegation SAS発行
  -> Browser direct PUT to Public Ingest Storage
  -> upload-complete
  -> Durable Functions orchestration
  -> m4a/mp4 preprocessing to ingest FLAC if needed
  -> Fast Transcription audioUrl + diarization
     or Batch Transcription fallback for long/large stable-route audio
     or Content Understanding video analyzer for experimental route
  -> normalized transcriptをArtifact Storageへ保存（分離前は既存Storage）
  -> direct minutes generation
  -> minutes schema validation
  -> Markdown rendering
  -> Artifact Storage（分離前は既存Storage）/ Cosmos DBへ結果保存
  -> UI pollingで表示
```

UIには右サイドドロワー型の「仕組みガイド」を実装している。ナビゲーションまたはheroから開き、標準経路、Batch fallback、動画理解（実験）、Azure構成、セキュリティ境界をアプリ内で説明できる。閉じている間はメイン操作を邪魔せず、デモ時だけ補助説明として使う。

## 3. Azureリソースと責務

| リソース | 主な責務 |
|---|---|
| Azure App Service | React UI配信、共有アクセスキーのゲート、`/api` reverse proxy |
| Azure Functions Premium | HTTP API、Durable Functions Activity/Orchestrator |
| Durable Task Scheduler | orchestration state、checkpoint、retry管理 |
| Public Ingest Storage | raw audio、Speech/CUが読む入力、標準経路の前処理済みFLAC |
| Private Artifact Storage（中期/有効化時） | raw/normalized transcript、minutes JSON/Markdown、visual context |
| Azure Cosmos DB for NoSQL | job state、progress、outputs、speaker mapping |
| Azure Speech in Foundry Tools | Fast Transcription + diarization |
| Azure Speech Batch Transcription | 2時間超〜4時間未満の標準経路fallback |
| Azure OpenAI in Microsoft Foundry Models | direct minutes generation、chunk fallback |
| Microsoft Foundry project `minutes-studio` | new Foundry portalでのデモ/実験整理。runtime APIはAIServices account-level endpointを継続 |
| Application Insights / Log Analytics | traces、duration telemetry、障害調査 |
| Managed Identity / Azure RBAC | Storage/Cosmos/Speech/OpenAIへのkeylessアクセス |

## 4. 認証・アクセス制御

### デモUIゲート

App Service側のExpress serverが `/login` で共有アクセスキーを検証し、HttpOnly Cookieを発行する。これは顧客デモ用の簡易ゲートであり、本番向けのユーザー認証ではない。

### Frontend -> Functions

ブラウザはFunctionsのURLを直接叩かず、App Serviceの `/api` reverse proxy 経由で呼び出す。App ServiceはFunctions呼び出し時に内部ヘッダー `x-proxy-secret` を付与し、Functions側で検証する。

### Functions -> Azureリソース

Functionsはmanaged identityを使い、Storage/Cosmos DB/Azure Speech/Azure OpenAIへアクセスする。Storage account keyを使ったSAS発行は新規実装しない。

## 5. データフローと機密情報

ブラウザはUser Delegation SASを使ってBlobへ直接PUTする。APIサーバーは大きな音声ファイル本体を中継しない。

ログに出してはいけないもの:

- 音声本文
- transcript全文
- minutes全文
- SAS URL全文
- Authorization header / token
- API key / Storage account key / client secret

Application InsightsではActivity durationやjobIdなどの運用メタデータだけを追跡する。本文データは出さない。

## 6. 音声処理方式

標準経路は、録音済み音声を正として、話者分離付きtranscriptと議事録を安定生成する本線である。ブラウザはAPIからUser Delegation SASを受け取り、Functionsを経由せずPublic Ingest Storageへ直接PUTする。APIは大容量ファイル本文を中継しない。

`POST /api/jobs` では拡張子、Content-Type、申告サイズ、クライアント推定durationを検証し、アップロードSASを発行する。`upload-complete` では実Blobサイズを確認してからDurable orchestrationを開始する。durationはブラウザ推定値を参考にし、最終的な長さ境界は前処理後メタデータとSpeech/Batch側の制限で判定する。

文字起こしは、音声全体を Azure Speech in Foundry Tools Fast Transcription に1回投入する。`diarization.enabled=true` を使い、`channels` は指定しない。

音声をチャンク分割して並列文字起こししない理由:

- チャンクごとにspeaker labelが再割り当てされる可能性がある。
- `Speaker 1` が会議全体で同一人物とは限らなくなる。
- speaker reconciliationの追加設計が必要になる。
- 現要件では話者分離品質を優先する。

m4a/mp4はFast Transcriptionで直接失敗するケースがあるため、必要に応じてffmpegで音声トラックだけを16kHz mono FLACへ前処理してからSpeechへ渡す。前処理済みFLACはSpeech/CUが参照できるPublic Ingest Storageへ保存し、read SASを発行する。MP4に音声トラックがない場合は前処理エラーにする。標準経路では映像を議事録本文の根拠にしない。

Fast Transcriptionの上限を超える標準経路入力では、Batch Transcription fallbackへ自動切替する。Batch REST APIは `/speechtotext/transcriptions:submit?api-version=2024-11-15` を使い、`properties.diarization.enabled=true` と `maxSpeakers` を送る。`channels` は指定しない。結果取得では `kind: "Transcription"` のファイルだけを正規化し、Batch結果の `source` は入力SASを含み得るためartifact保存前に除去する。

Fast/Batchのどちらでも、音声全体を1つの入力として扱う。これは、音声チャンクごとにspeaker labelが再割り当てされることを避けるためである。議事録生成段階のchunk fallbackは、文字起こし済みテキストを分ける処理であり、音声STT入力の分割とは別レイヤである。

## 7. 議事録生成方式

本線は direct minutes generation。

```text
normalized transcript全文
-> Azure OpenAI in Microsoft Foundry Models
-> minutes.structured-output.schema.json
-> minutes.schema.jsonで保存前検証
```

UIから選べるモード:

| UI | API値 | 用途 |
|---|---|---|
| 高速 | `fast` | 既定。GPT-5.4 miniで低レイテンシ |
| 高品質 | `quality` | GPT-5.4で品質重視 |

raw transcription resultは、phraseごとのspeaker/timestamp/text/confidenceを `normalized-transcript.schema.json` に揃える。議事録生成では、このnormalized transcriptを根拠にStructured outputsでminutes JSONを生成する。transcriptにない担当者・期限・参加者名は推測で補完しない。

direct生成が出力切れ、token制約、JSON破損、schema repair失敗などの回復可能な制約に当たった場合のみ、chunk summary方式へ自動fallbackする。通常のOrchestrator本線ではchunk Activityを呼ばない。長尺Batch transcriptでも、議事録生成側の制約に当たればこのテキストchunk fallbackで回復する。

これは議事録生成のchunk fallbackとは別で、文字起こしエンジンのfallbackである。Batchはキュー待ちを含め最大24時間かかる可能性があるため、入力Blob read SASはBatch専用に既定25時間TTLで発行する。

## 7.1 Content Understanding動画理解経路（実験）

UIでは標準経路に加え、動画理解（実験）経路を選べる。実験経路では元MP4を Content Understanding video analyzer に渡し、`transcriptPhrases` を normalized transcript に変換して既存のminutes generatorへ渡す。key frames / camera shots / visual fields / markdown は visual context artifact として保存し、UIの「映像メモ」タブに表示する。

Phase 1では、映像由来の情報を議事録本文の決定事項/ToDo/期限/担当者の根拠にはしない。映像情報は補足情報として人間が確認する。

## 8. 性能と計測

約55分m4aの計測例はADR-007に記録している。代表値は次の通り。1回計測であり、SLAではない。

| 方式 | E2E | 備考 |
|---|---:|---|
| 旧chunk本線 | 224.6s | chunk summary + final merge |
| direct fast | 163.1s | 低レイテンシ。出力は薄めになる場合あり |
| direct quality | 194.8s | 旧方式より短く、出力は比較的充実 |

最新のボトルネックは主にSpeech処理。議事録生成はdirect fastで大きく短縮済み。

Activity別の時間はApplication Insightsのtraceで確認する。詳細KQLは `docs/07-security-and-operations.md` を参照。

## 9. 制限と設計上の境界

| 項目 | 現在の扱い |
|---|---|
| 音声長 | 標準経路は4時間未満までBatch fallback候補。CU経路は120分まで |
| 標準経路の直接音声入力 | 1GB未満。500MB超はBatch fallback候補 |
| 標準経路のm4a/mp4元ファイル | 4GB未満。抽出後音声がFast上限超ならBatch fallback |
| Content Understanding経路のファイルサイズ | 4GB未満（Blob URL参照Analyze API） |
| Speech timeout | 480秒 |
| リアルタイム音声 | 対象外 |
| 音声チャンク並列STT | 話者分離品質リスクのため本線では不採用 |

120分はFast Transcription diarizationおよびContent Understanding video URL参照の2時間境界に近い。標準経路ではFast上限を超える場合Batch fallbackへ切り替えるが、CU経路では120分近傍はサービス制限やファイル内容により失敗する可能性がある。256MB超のファイルはブラウザからBlobへブロック分割アップロードする。再開機能までは未実装のため、ネットワーク中断時は再実行が必要。実用上はより小さい動画でのデモを推奨する。

## 10. 運用チェックリスト

デプロイ・運用時は次を確認する。

1. App Serviceの共有アクセスキーとFunctions用proxy secretが別値で設定されている。
2. Functionsのmanaged identityにStorage/Cosmos DB/Speech/OpenAIの必要ロールがある。
3. Ingest Blob public endpointが、ブラウザ直接アップロード、Speech `audioUrl`、Content Understanding URL参照に必要な範囲で有効。
4. private Artifact Storageを有効化する場合、Functions VNet Integration、Private DNS、Blob Private Endpoint経由でtranscript/minutes/visual contextを保存・取得できる。
5. Cosmos DBをprivate化する場合、Private Endpoint疎通確認後にpublic accessを無効化している。
6. Storage account keyを使ったSAS発行をしていない。
7. Function App CORS / Storage CORSがfrontend originに限定されている。
8. Application InsightsにSAS URL全文、token、key、音声本文、transcript全文、minutes全文が出ていない。
9. 短い音声でE2E smokeを実施し、`DONE`、transcript取得、minutes取得を確認する。
10. 代表的な長尺音声でfast/qualityの時間と品質を確認する。

## 11. 詳細ドキュメントへのリンク

- `docs/00-design-summary.md` - 全体設計サマリー
- `docs/02-architecture.md` - Azureアーキテクチャ
- `docs/05-workflow-spec.md` - Durable Functions workflow
- `docs/06-ai-and-prompts.md` - AI処理・プロンプト仕様
- `docs/07-security-and-operations.md` - セキュリティ・運用・KQL例
- `docs/13-deployment-plan.md` - デプロイ計画
- `docs/adr/007-direct-minutes-generation-with-chunk-fallback.md` - direct生成採用のADR
