# 00. 設計サマリー

確認日: 2026-06-01

## 結論

本システムは、**録音済み音声ファイルを非同期ジョブとして処理する議事録生成システム**として実装する。主経路は次の通り。

```text
Direct-to-Blob upload
  -> upload-complete API
  -> Durable Functions orchestration
  -> Azure Speech in Foundry Tools Fast Transcription + diarization
  -> normalized transcript
  -> Azure OpenAI in Microsoft Foundry Models v1 API による議事録生成
  -> speaker mapping UI
  -> final minutes
```

2026-06-01時点のdev MVPは `westus3` / `<resource-group>` にデプロイ済み。Frontend App Service、Azure Functions Premium EP1、Blob Storage、Cosmos DB、AIServices、Application Insights を使い、短い日本語TTS音声の live E2E は `DONE` まで到達した。

## 最重要設計判断

### 1. 文字起こしは全体音声に対して1回だけ実行する

80分音声は、Fast Transcription の diarization 有効時条件である2時間未満に収まる。音声をチャンク分割して並列に文字起こしすると、チャンク間の speaker ID を統合する処理が必要になる。そのため、初期実装では全体音声を1回だけ Fast Transcription に投入する。

### 2. 議事録生成だけを並列化する

文字起こし結果は speaker ID と timestamp を含む transcript として保存する。その transcript を 5〜10分相当の論理チャンクに分割し、Durable Functions の `task_all` で `GenerateChunkSummaryActivity` をfan-outする。最後に全体統合を1回行う。

### 3. UXは「完了までの待ち時間短縮」だけでなく「途中成果物の表示」で改善する

Fast Transcription 完了後、まず transcript を表示する。次にチャンク要約が終わった順に暫定要約を表示する。最後に統合版の議事録を表示する。初期実装は Durable Functions status endpoint / Cosmos状態のポーリングでよい。ポーリング間隔は状態に応じてbackoffし、必要になった段階で Azure SignalR Service へ置き換える。

### 4. 入力上限はサービス上限とUX上限を分ける

サービス上限としては、Fast Transcription は500MB未満・5時間未満、diarization 有効時は2時間未満。ただし、UXの安定性を重視し、初期リリースの通常受付は300MB未満・2時間未満にする。300MB〜500MBのファイルは、管理者許可、圧縮、またはエラー誘導にする。

### 5. 本番化前に認証を切り替える

現在のdev MVPは `MEETING_MINUTES_AUTH_MODE=demo` により固定の `demo-tenant` / `demo-user` で動く。Azure環境では `x-dev-tenant-id` / `x-dev-user-id` を信用しないが、HTTP trigger + demo認証は本番・実データ・広範な共有利用には不十分。実利用前に Microsoft Entra ID / Easy Auth 強制とユーザー単位認可を完了する。

## 現在のdev MVP実装状況

| 項目 | 現状 |
|---|---|
| Frontend | `https://<web-app-name>.azurewebsites.net/` |
| Backend | `https://<function-app-name>.azurewebsites.net/api/health` |
| Backend runtime | Azure Functions Premium EP1 / Python 3.13 |
| Function registration | Azure上は v1 `function.json` wrappers。`function_app.py` はローカル・テスト用 |
| AI resource | AIServices `<ai-services-name>` |
| Deployments | `gpt-5.4-mini`, `gpt-5.4`、GlobalStandard capacity 100 each |
| 実装済みAPI | `POST /api/jobs`, `POST /api/jobs/{jobId}/upload-complete`, `GET /api/jobs/{jobId}`, `GET /api/jobs/{jobId}/transcript`, `GET /api/jobs/{jobId}/minutes` |
| E2E | 短い日本語TTS音声と55分m4a音声で `DONE`、transcript/minutes取得、chunk/chunk summary Blob保存を確認済み |

## 初期スコープ

| 項目 | 初期実装 |
|---|---|
| 入力 | 音声ファイル。API受付は `.mp3`, `.wav`, `.m4a`, `.ogg`, `.webm`, `.flac`。E2E確認済みは短いWAVとm4a→FLAC前処理経路 |
| 音声長 | 2時間未満 |
| 通常ファイルサイズ | 300MB未満 |
| 話者分離 | あり。speaker ID は匿名ラベルとして扱う |
| 実名紐付け | UIで後から user が指定する |
| 文字起こし | Azure Speech in Foundry Tools Fast Transcription |
| 議事録生成 | Azure OpenAI in Microsoft Foundry Models |
| 状態表示 | ポーリング。将来 SignalR |
| 監視 | Application Insights |

## 非スコープ

- 話者の実名識別。diarization は個人識別ではない。
- リアルタイム会議音声の逐次処理。
- 文字起こし前の音声チャンク並列化。
- MAI-Transcribe-1 の主経路利用。diarization 非対応のため。
- Batch Transcription の主経路利用。ピーク時遅延が大きいため。

## リスクと対策

| リスク | 影響 | 対策 |
|---|---:|---|
| demo認証のまま本番利用される | 高 | 本番化ブロッカーとして明記。Microsoft Entra ID / Easy Auth とuser単位認可が完了するまで実データ利用しない |
| 音声品質が悪く文字起こし精度が下がる | 高 | 音声品質チェック、phrase list、LLM Speech比較、手動修正UI |
| speaker ID が実名と一致しない | 高 | 実名識別しない。UIで speaker mapping を登録 |
| 300MB超の音声で待ち時間が長い | 中 | UX上限を300MBに設定。圧縮・再アップロードを促す |
| Azure OpenAIのTPM/RPM不足 | 高 | `gpt-5.4-mini` / `gpt-5.4` capacity 100をdevで設定済み。チャンク並列度制御、指数バックオフ、クォータ監視 |
| Storage public endpointが無効化される | 高 | Fast Transcription `audioUrl` とブラウザ直接アップロードの前提。Bicepで `publicNetworkAccess=Enabled` を明示し、Policy/手動変更によるドリフトを監視 |
| HTTP要求がタイムアウトする | 高 | `202 Accepted` + Durable Functions 非同期パターン |
| Blob SAS漏えい | 高 | User Delegation SAS、短時間TTL、最小権限、HTTPSのみ。Application InsightsでSAS/query漏えいを継続スキャン |

## 完了済みと次の優先課題

完了済み:

1. API: ジョブ作成、SAS発行、アップロード完了、状態取得、transcript取得、minutes取得。
2. Durable workflow: validate -> transcribe -> normalize -> `task_all` chunk summaries -> final merge -> render/persist。
3. Speech client: Fast Transcription + diarization の live E2E。
   - m4aはFast Transcription直渡しでデコードできないケースがあるため、Backendで16kHz mono FLACへ前処理する。
4. Minutes generator: Structured outputs 用schemaによるJSON固定、保存前schema検証、Markdownコード生成。
5. UI: アップロード、進捗、transcript/minutes表示のdev MVP。
6. Observability: Application Insightsで機密ログ漏えいスキャンを実施し、主要secretやSAS全文の未検出を確認。

次の優先課題:

1. Microsoft Entra ID / Easy Auth 強制、demo認証の廃止、他ユーザーjobアクセス拒否テスト。
2. 代表的な短い会議音声fixtureと品質期待値を整備し、E2E回帰テストを安定化。
3. ポーリングbackoff、チャンク並列度、429率、total seconds の性能回帰基準を定義。
4. 80分音声の代表E2Eで処理時間・品質・コストを測定し、本番既定モデル/容量をADR化。
