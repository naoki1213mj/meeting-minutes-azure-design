# Azure 議事録生成システム

確認日: 2026-06-01  
対象: 録音済み音声ファイルを入力し、話者分離付きの文字起こしと議事録を非同期に生成する Azure MVP。

## 結論

初期実装は、**全体音声を Azure Speech in Foundry Tools の Fast Transcription に1回投入し、diarization を有効にする**方式に固定する。音声のチャンク分割文字起こしは初期実装から外す。議事録生成だけを、話者分離済み transcript の論理チャンク単位で並列化する。

理由:

- Fast Transcription は、録音済み音声の transcript を同期的に、リアルタイムより速く返す用途に向いている。
- diarization を音声チャンクごとに実行すると、チャンク間で speaker ID の整合性を保証しにくい。
- 80分音声は diarization 有効時の2時間未満条件に収まる。
- 体感UXの短縮は、直接アップロード、即時ジョブ開始、進捗表示、transcript先出し、議事録生成のチャンク並列化で実現する。

## 現在のdev MVP状態

| 項目 | 現状 |
|---|---|
| Subscription | `<subscription-id>` |
| Resource group | `<resource-group>` |
| Region | `westus3` |
| Frontend | `https://<web-app-name>.azurewebsites.net/` |
| Backend health | `https://<function-app-name>.azurewebsites.net/api/health` |
| Backend hosting | Azure Functions Premium EP1 / Python 3.13 |
| Function registration | Azure上は v1 `function.json` wrappers。`function_app.py` はローカル・テスト用で `.funcignore` によりデプロイ対象外 |
| Microsoft Foundry resource | AIServices `<ai-services-name>` |
| Model deployments | `gpt-5.4-mini`, `gpt-5.4`、GlobalStandard capacity 100 each |

実装済みAPI:

- `POST /api/jobs`
- `POST /api/jobs/{jobId}/upload-complete`
- `GET /api/jobs/{jobId}`
- `GET /api/jobs/{jobId}/transcript`
- `GET /api/jobs/{jobId}/minutes`

TTSで生成した短い日本語音声と、55分のm4a音声の live E2E は `DONE` まで到達し、transcript/minutes取得、chunkおよびchunk summary Blob保存、schema validation が確認済み。m4aはBackendで16kHz mono FLACへ前処理してから Azure Speech in Foundry Tools へ渡す。

> **本番化ブロッカー:** 現在のdev MVPは `MEETING_MINUTES_AUTH_MODE=demo` により固定の `demo-tenant` / `demo-user` で動く。Azure環境では `x-dev-tenant-id` / `x-dev-user-id` を信用しないが、HTTP trigger + demo認証は本番・実データ・広範な共有利用には安全ではない。実利用前に Microsoft Entra ID / Easy Auth を強制し、ユーザー単位認可へ切り替えること。

## リポジトリ構成

```text
.
├── AGENTS.md
├── README.md
├── .env.example
├── azure.yaml
├── backend/
├── frontend/
├── infra/
├── docs/
└── specs/
```

詳細な設計・仕様は `docs/` と `specs/` を正とする。

## 技術スタック

- バックエンド: Python 3.13、Azure Functions、Durable Functions、uv
- フロントエンド: TypeScript、React、Vite
- ストレージ: Azure Blob Storage
- ジョブDB: Azure Cosmos DB for NoSQL
- 文字起こし: Azure Speech in Foundry Tools Fast Transcription + diarization
- 議事録生成: Azure OpenAI in Microsoft Foundry Models v1 API
- 監視: Azure Monitor Application Insights
- インフラ: Bicep、Azure Developer CLI

## ローカル開発コマンド

バックエンド:

```powershell
cd backend
uv sync
uv run pytest
uv run ruff check .
uv run mypy .
uv run python ..\scripts\validate_specs.py
```

フロントエンド:

```powershell
cd frontend
npm install
npm run typecheck
npm test
npm run build
```

Azure Developer CLI:

```powershell
azd env new dev --no-prompt
azd env set AZURE_SUBSCRIPTION_ID "<subscription-id>"
azd env set AZURE_LOCATION "westus3"
```

2026-06-02時点の確認実績は、バックエンド83 tests + ruff + mypy + schema validation、フロントエンド18 tests + typecheck + build、live E2E smoke 成功。

## GitHub Actions CI/CD設計

現時点で `.github/workflows/` は未作成のため、まずは設計として次の構成にする。

- PR CI: Python 3.13 exactly / Node 20で、backend lint/type/test/schema、frontend type/test/build、Bicep buildを実行する。PR実行は `cancel-in-progress: true` でよい。
- dev deploy: `main` へのmerge後、CI成功を条件に GitHub OIDC + `azure/login` + `azd` で `azd provision --no-prompt`、`azd deploy backend`、`azd deploy frontend` を実行する。
- prod deploy: GitHub Environment `prod` のrequired reviewers、保護ブランチ/タグ、手動 `workflow_dispatch` を必須にする。現在の `MEETING_MINUTES_AUTH_MODE=demo` は本番化ブロッカーなので、Easy Auth / Microsoft Entra ID 強制とdemo認証無効化までprod deployは禁止する。
- 認証はOIDCのみ。client secret、publish profile、`AZURE_CREDENTIALS`、API key、Storage key、SAS URLはGitHub Secretsへ保存しない。
- 詳細なOIDC subject、RBAC、検証マトリクス、運用手順は `docs/07-security-and-operations.md`、`docs/09-test-plan.md`、`docs/13-deployment-plan.md` を正とする。

## 実装の本線

```text
1. ユーザーがWeb UIで音声を選択
2. APIがジョブを作成し、User Delegation SAS のアップロードURLを返す
3. ブラウザがBlob Storageへ直接アップロード
4. ブラウザが upload-complete API を呼ぶ
5. Durable Functions が非同期ジョブを開始し、202 Accepted を返す
6. 入力を検証
7. m4aの場合はBackendで16kHz mono FLACへ前処理する
8. Fast Transcription + diarization を全体音声に1回実行
9. transcript を正規化して保存
10. transcript を論理チャンクに分け、Durable task_all で議事録要素を並列抽出
11. 最終議事録JSONを統合生成
12. アプリ側で jobId, tenantId, generatedAt などを付与して最終schema検証
13. Markdown / DOCX 用データに整形
14. UIで話者名を紐付け、必要なら議事録表示を更新
```

## パフォーマンス方針

- 文字起こしは全体音声1回に固定し、speaker ID の整合性を守る。
- 議事録生成は `BuildTranscriptChunksActivity` → `GenerateChunkSummaryActivity` の fan-out/fan-in で並列化する。
- `gpt-5.4-mini` / `gpt-5.4` はdev環境で capacity 100 に増強済み。長尺音声のfinal mergeで429が出たため、TPM余裕を持たせる。429発生時は指数バックオフと並列度制御で吸収する。
- UIポーリングは短い固定間隔ではなく、状態に応じたbackoffを推奨する。

## セキュリティ方針

- User Delegation SAS を使い、Storage account key を使ったSASを新規実装しない。
- Fast Transcription `audioUrl` とブラウザ直接アップロードのため、dev MVPのStorage Blobデータ面はpublic endpointを有効にする。Blob匿名公開と共有キーは無効化し、保護はUser Delegation SASと短いTTLで行う。
- 音声本文、transcript全文、議事録全文、SAS URL全文、アクセストークン、API key、Storage account key をログに出さない。
- Application Insights のlive E2E後スキャンでは、SAS/query/audio/upload URL/API key/access token/client secret/Bearer token は検出されず、Azure SDK Authorization traces はredact済みだった。
- 本番前に Microsoft Entra ID / Easy Auth、ユーザー単位認可、他ユーザーjobアクセス拒否テストを必須にする。

## 対応ファイル形式

アップロードAPIが受理する拡張子は `.mp3`, `.wav`, `.m4a`, `.ogg`, `.webm`, `.flac`。`application/octet-stream` はこの拡張子に限って受け付ける。`.mp4` 動画はバリデーションで拒否する。

live E2Eで確認済みの標準経路は、短いWAV音声と、m4a音声の16kHz mono FLAC前処理経路。mp3/ogg/webm/flacの直接経路は受理対象だが、代表音声での回帰確認を追加するまでは未検証扱いにする。

## 初期実装でやらないこと

- 音声チャンクごとの並列文字起こし
- Batch Transcription の主経路化
- MAI-Transcribe-1 の利用
- リアルタイム会議音声の逐次文字起こし
- 話者の実名自動識別
- 完全閉域構成
- 複雑な承認ワークフロー

## 重要な制限値と実装上の扱い

- Fast Transcription のサービス制限: 500MB未満、5時間未満。diarization 有効時は2時間未満。
- 初期UX上限: 300MB未満、2時間未満。300MB超は圧縮または管理者許可制。
- 本番の Fast Transcription は `audioUrl` 方式を使う。長い音声では public URL からのアップロードが推奨されるため。
- REST API の inline `audio` 方式は小さい開発・検証用に限定する。大きい音声を inline で送る実装はしない。
- Azure OpenAI in Microsoft Foundry Models は v1 API を使う。新規実装で dated `api-version` を増やさない。
- Structured outputs には `specs/*.structured-output.schema.json` を使う。最終保存前の厳密検証には `specs/minutes.schema.json` を使う。
- Azure Functions HTTP 応答は最大230秒。長時間処理は Durable Functions の非同期パターンにする。

詳細は `docs/10-official-references.md` と `docs/11-review-findings-2026-05-31.md` を参照。
