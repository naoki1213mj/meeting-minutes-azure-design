# 01. 要件定義

確認日: 2026-06-01

## 1. 背景

ユーザーは80分程度の録音済み音声ファイルをアップロードし、話者分離付きの文字起こしと議事録を得たい。UXとして、入力から出力までの時間をできるだけ短くしたい。

## 2. ペルソナ

### 会議参加者

- 会議後に音声ファイルをアップロードする。
- 数分単位で進捗を確認したい。
- 議事録をそのまま共有できる形にしたい。
- speaker ID を実名に直したい。

### 管理者

- 失敗ジョブの原因を確認したい。
- コスト、処理時間、エラー率を監視したい。
- 入力上限やモデルを設定したい。

## 3. 機能要件

### FR-001: 音声アップロード

ユーザーはWeb UIから音声ファイルを選択し、Blob Storageへ直接アップロードできる。

受け入れ条件:

- APIはアップロード用の短時間SAS URLを返す。
- ブラウザはAPIサーバーを経由せずBlobへアップロードする。
- アップロード完了後、`upload-complete` APIを呼ぶ。

### FR-002: 入力検証

システムは音声ファイルの拡張子、サイズ、想定音声長を検証する。

受け入れ条件:

- 通常受付は300MB未満、120分以下。
- 300MB〜500MBは管理者設定により許可可能。
- 120分超は Fast Transcription + diarization の主経路では受け付けない。120分近傍はbest effortとして扱う。
- 不正な形式は、ユーザーに再アップロードを促す。

### FR-003: 話者分離付き文字起こし

システムは Azure Speech Fast Transcription に diarization 有効で音声を投入する。

受け入れ条件:

- `diarization.enabled = true` を設定する。
- `maxSpeakers` を設定できる。未指定時は8を既定値にする。
- `locales` は既定で `ja-JP` を設定する。
- 結果に speaker ID と timestamp を含める。

### FR-004: transcript 正規化

Speech API の応答を、アプリ共通の `normalized-transcript.schema.json` に変換する。

受け入れ条件:

- phrase 単位で `speakerLabel`, `offsetMilliseconds`, `durationMilliseconds`, `text` を保存する。
- 元の API response も Blob に保存する。
- 正規化済み transcript は Cosmos DB にメタデータ、Blob に本文を保存する。

### FR-005: 議事録生成

システムは normalized transcript から議事録を生成する。

受け入れ条件:

- transcript を論理チャンクに分割する。
- 各チャンクから要点、決定事項、ToDo、未決事項、引用 timestamp を抽出する。
- 最終統合では `minutes.structured-output.schema.json` に準拠したLLM応答を生成する。
- アプリ側で metadata を付与し、保存前に `minutes.schema.json` で検証する。
- JSONからMarkdownを生成する。

### FR-006: 進捗表示

ユーザーはジョブの現在状態を確認できる。

受け入れ条件:

- APIはジョブ状態を返す。
- UIは2〜5秒間隔でポーリングする。
- 状態は `CREATED`, `UPLOADING`, `UPLOADED`, `VALIDATING`, `TRANSCRIBING`, `TRANSCRIPT_READY`, `GENERATING_CHUNK_SUMMARIES`, `GENERATING_FINAL_MINUTES`, `DONE`, `FAILED` などを表示する。UI表示名は「議事録生成中」のようにまとめてもよいが、内部状態は `specs/job-status.schema.json` のenumに合わせる。

### FR-007: speaker mapping

ユーザーは `Speaker 0` などの匿名ラベルを実名に紐付けられる。

受け入れ条件:

- UIは各 speaker の代表発話を3〜5件表示する。
- ユーザーは表示名を入力できる。
- speaker mapping 変更後、議事録の話者表示を更新できる。
- 必要なら議事録を再生成できる。

### FR-008: ダウンロード

ユーザーは議事録をMarkdownまたはDOCX相当の形式で取得できる。

受け入れ条件:

- 初期実装はMarkdownを必須とする。
- DOCX生成は後続タスクにしてもよい。
- transcript JSON と minutes JSON は管理者向けにダウンロード可能にする。

## 4. 非機能要件

### NFR-001: レイテンシ

80分・300MB未満の音声で、アップロード完了後から議事録表示までの時間を短くする。初期PoCでは絶対SLAは置かず、以下を個別計測する。

- upload seconds
- validation seconds
- transcription seconds
- transcript normalization seconds
- chunk summary seconds
- final merge seconds
- total seconds

### NFR-002: 可用性

- 各ジョブは再試行可能にする。
- Speech API の429/5xxは指数バックオフで再試行する。
- 失敗時は原因コードとユーザー向けメッセージを保存する。

### NFR-003: セキュリティ

- Blob Storageへの直接アップロードにはUser Delegation SASを使う。
- SASは短時間TTL、最小権限、HTTPS前提にする。
- Speech/OpenAI/Storageへのアクセスは可能な限りMicrosoft Entra IDとmanaged identityを使う。
- 音声ファイル、transcript、議事録は顧客データとして扱う。

### NFR-004: 監査

- jobId, tenantId, userId, audioSizeBytes, audioDurationSeconds, modelDeployment, tokenUsage, retryCount を記録する。
- 音声本文や全文transcriptをログに出さない。
- Application Insights の sampling に注意する。

### NFR-005: 保守性

- Azure SDK呼び出しは repository/service 層に閉じ込める。
- プロンプトはコードから分離する。
- JSON Schema は `specs/` を正とする。

## 5. 制約

- 文字起こしは録音済み音声を対象にする。
- 話者分離は話者識別ではない。実名推定はしない。
- 300MB超は初期UXでは標準受付しない。
- 2時間以上の音声は Fast Transcription + diarization の標準経路では処理しない。

## 6. 成功指標

| 指標 | 目標 |
|---|---:|
| 80分音声の文字起こし成功率 | PoCで95%以上を目指す |
| 議事録JSON Schema検証成功率 | 99%以上 |
| ユーザーによるspeaker修正回数 | 記録のみ。改善指標にする |
| 文字起こし失敗時の原因分類率 | 100% |
| 音声本文のログ混入 | 0件 |
