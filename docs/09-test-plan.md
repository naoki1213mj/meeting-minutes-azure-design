# 09. テスト計画

確認日: 2026-06-01

## 1. テスト方針

- API、workflow、AI出力、UIを分けてテストする。
- Azure依存部分はインターフェース化し、単体テストではモックする。
- E2Eは小さい音声ファイルから始め、PoCで実80分音声を使う。
- 自動生成議事録は、構造検証と人手評価の両方で確認する。
- 本番化前に Microsoft Entra ID / Easy Auth とユーザー単位認可のテストを必須にする。
- 性能・セキュリティ・機密ログ漏えい検査を回帰テストに含める。

## 2. 現在の検証実績

| 種別 | コマンド / 確認 | 期待値 / 実績 |
|---|---|---|
| Backend unit/lint/type/schema | `uv run pytest --quiet`; `uv run ruff check . --quiet`; `uv run mypy .`; `uv run python ..\scripts\validate_specs.py` | 2026-06-02時点で83 tests、lint/type/schema validation成功 |
| Frontend type/test/build | `npm run typecheck`; `npm test`; `npm run build` | 2026-06-02時点で22 tests、typecheck/build成功 |
| API smoke | `POST /api/jobs`; `POST /api/jobs/{jobId}/upload-complete`; `GET /api/jobs/{jobId}` | dev live環境で成功 |
| Result retrieval | `GET /api/jobs/{jobId}/transcript`; `GET /api/jobs/{jobId}/minutes` | dev live E2Eで取得成功 |
| Live E2E | TTSで生成した短い日本語音声 | `DONE` 到達、normalized transcript / minutes schema validation成功、direct minutes generation確認 |
| Telemetry scan | Application Insights検索 | SAS/query/audio/upload URLs、API keys、access tokens、client secrets、Bearer tokens未検出。Azure SDK Authorization tracesはredact済み |

今回のドキュメント更新ではアプリケーションコードを変更しない。コード変更時は上記の該当コマンドを再実行する。

## 3. 単体テスト

### Backend

| 対象 | テスト |
|---|---|
| Job repository | create, get, update status, idempotency |
| SAS issuer | 権限、TTL、Blob pathの正しさ、User Delegation SASであること |
| ValidateInput | サイズ、拡張子、duration、locale、maxSpeakers |
| Speech client | `audioUrl` request body、`channels`未指定、リトライ、エラー正規化、機密ログ抑止 |
| Transcript normalizer | raw responseからschema準拠JSONへの変換 |
| Chunker | 時間境界、phrase分割回避、chunk数、deterministic blob path |
| Minutes generator | schema validation、修復、禁止推測、deployment capabilityに基づく生成パラメーター |
| Markdown renderer | JSONから安定したMarkdown生成 |
| Auth middleware | demo/auth mode切替、header spoofing拒否、本番modeでtoken必須 |

### Frontend

| 対象 | テスト |
|---|---|
| ファイル選択 | サイズ/拡張子チェック |
| Upload component | 進捗表示、失敗表示 |
| Job status view | 状態ごとの表示、polling backoff |
| Transcript view | speaker/timestamp表示 |
| Speaker mapping | 入力、保存、反映 |
| Minutes view | Markdown表示 |
| Auth integration | Easy Auth/Entra ID有効時の未認証導線、ログアウト、権限不足表示 |

## 4. 結合テスト

### 仕様整合

- `specs/job-status.schema.json` のstatus enum、`specs/openapi.yaml` のJobStatus参照、`docs/04-data-model.md` のstatus表が矛盾しない。
- `specs/openapi.yaml` の `JobStatus` は `specs/job-status.schema.json` を参照する。
- OpenAPI内の `JobStatusEnum` と `specs/job-status.schema.json#/properties/status/enum` が完全一致する。
- `specs/minutes.schema.json` と `docs/04-data-model.md` のMinutes JSON必須項目が矛盾しない。
- Python 3.13で `uv run pytest`, `uv run ruff check .`, `uv run mypy .` が動作する。
- Python 3.13で主要Azure/Pydantic/OpenAI依存が解決できる。

### API + Blob

- `POST /api/jobs` でSAS URLが返る。
- SASでBlobへPUTできる。
- upload-completeでジョブが開始する。
- Blob pathがjobIdのスコープに閉じる。
- SAS URL全文がログ・例外・Application Insights custom dimensionsに出ない。

### Durable workflow

- スタブSpeech responseで `DONE` まで進む。
- Activity失敗時に `FAILED` になる。
- retry対象エラーで再試行される。
- 同一jobIdの二重実行が起きない。
- 本線では `NormalizeTranscriptActivity` 後に `GenerateFinalMinutesActivity` がdirect generationとして呼ばれる。
- direct generationが出力切れ・token制約・schema repair不能などで失敗した場合、chunk summary fallbackへ切り替わる。
- fallback時のchunk summaryが429/5xxになってもretry policyに従う。

### Speech連携

- 短い日本語音声で文字起こしできる。
- diarization有効時に speaker が含まれる。
- `channels` を指定しない。
- raw responseがBlobに保存される。
- `audioUrl` SAS TTLがSpeech fetch/retry中に切れない。

### OpenAI連携

- direct minutes generationが `minutes.structured-output.schema.json` に従う。
- fallback時のchunk summaryが `chunk-summary.structured-output.schema.json` に従う。
- final minutesのLLM応答が `minutes.structured-output.schema.json` に従う。
- metadata付与後のfinal minutesが `minutes.schema.json` に従う。
- schema validation失敗時に修復が1回実行される。
- `temperature` 等を全deploymentへ固定送信しない。
- 429発生時に指数バックオフし、必要ならchunk並列度を下げられる。

## 5. E2Eテスト

### E2E-001: 小さい音声

- 5分未満、20MB未満。
- アップロードからDONEまで完了する。
- transcript、minutes、markdownが生成される。
- `GET /api/jobs/{jobId}/transcript` と `GET /api/jobs/{jobId}/minutes` で取得できる。

### E2E-002: 代表的な短い会議音声

- 安定したfixtureをリポジトリ外または許可されたテストデータ保管場所で管理する。
- 期待される議題、決定事項、ToDo、speaker数を人手で定義する。
- 品質スコアとschema validationを回帰判定に使う。

### E2E-003: 80分音声

- 80分、300MB未満。
- Fast Transcription + diarization が成功する。
- 議事録が生成される。
- 処理時間が分解計測される。
- direct minutes generationとfallback発動有無のtoken/latency/costを記録する。

### E2E-004: サイズ超過

- 300MB超。
- 既定ではユーザーに圧縮を促す。
- 管理者許可設定がある場合のみ続行できる。

### E2E-005: 2時間超

- 2時間以上。
- Fast Transcription + diarization標準経路では拒否する。

### E2E-006: speaker mapping

- transcript生成後に `Speaker 0 = 山田さん` を保存。
- minutes表示に反映される。
- 必要なら議事録再生成が成功する。

## 6. セキュリティテスト

- SAS URLのTTLが短いこと。
- SAS権限が対象Blobに限定されること。
- SAS URL全文がログに出ないこと。
- 音声本文やtranscript全文がログに出ないこと。
- 議事録全文がログに出ないこと。
- 他ユーザーのjobIdにアクセスできないこと。
- 別tenantのjobIdにアクセスできないこと。
- Storage account keyをアプリ設定に置かないこと。
- Azure環境で `x-dev-tenant-id` / `x-dev-user-id` spoofingが効かないこと。
- 本番modeでanonymous requestが業務APIを実行できないこと。
- `MEETING_MINUTES_AUTH_MODE=demo` が本番slot/環境に設定されていないこと。
- Application InsightsにAPI key、access token、client secret、Bearer token、SAS query stringが残らないこと。

## 7. 負荷・性能テスト

PoCでは以下を測る。

| 条件 | 測定 |
|---|---|
| 同時1ジョブ | baseline |
| 同時5ジョブ | Speech/OpenAIレート制限 |
| 同時10ジョブ | Durable/Blob/Cosmos負荷 |
| capacity変更 | `gpt-5.4-mini` / `gpt-5.4` capacity 100で429率を確認 |
| polling backoff | UI/API呼び出し回数と体感UXを確認 |
| m4a/mp4前処理 | m4a/mp4から音声トラックを16kHz mono FLACへ変換し、Fast Transcriptionが完了すること |
| Storage public endpoint drift | `publicNetworkAccess=Enabled`, `allowSharedKeyAccess=false`, `allowBlobPublicAccess=false` が維持され、User Delegation SAS発行が403にならないこと |

計測値:

- upload seconds
- transcription seconds
- normalization seconds
- direct minutes seconds
- chunk summary seconds（fallback時）
- final merge seconds
- total seconds
- Speech 429回数
- OpenAI 429回数
- retryCount / backoff後成功率
- Cosmos DB RU消費
- chunk数、chunk並列度、token usage

### 7.1 添付m4a/mp4回帰

2026-06-02に55分m4a音声でlive E2Eを確認済み。回帰テストでは次を確認する。

- `POST /api/jobs` が `.m4a` / `audio/x-m4a` を `201` で受け付ける。
- `POST /api/jobs` が `.mp4` / `video/mp4` を `201` で受け付ける。
- m4a/mp4は `PREPROCESSING` を経由し、`preprocessed/{tenantId}/{jobId}/input.flac` が `audio/flac` で保存される。
- `DONE` 後に transcript と minutes を取得できる。
- 音声トラックがないMP4は `AUDIO_PREPROCESS_FAILED` で拒否される。
- 既に `FAILED` になったジョブはretry API未実装のため、同じファイルを再アップロードして確認する。

性能回帰の初期期待値:

- 通常時はdirect generationで完了する。
- fallback時はchunk summary fan-out/fan-inが機能する。
- 429が発生してもretry/backoffで回復し、継続的に失敗する場合は並列度を下げられる。
- UIポーリングは固定高頻度ではなく、状態変化が少ない区間でbackoffする。

## 8. 人手評価

実音声3本で評価する。

| 評価項目 | 5段階評価 | コメント |
|---|---:|---|
| 文字起こし精度 | 1〜5 | 固有名詞、専門用語 |
| 話者分離 | 1〜5 | speaker IDの切り替わり |
| 議事録の要約品質 | 1〜5 | 抜け漏れ、過剰要約 |
| 決定事項抽出 | 1〜5 | 正しさ |
| ToDo抽出 | 1〜5 | 担当者、期限 |
| 不要な推測の少なさ | 1〜5 | transcriptにない内容 |
| UX | 1〜5 | 待ち時間、進捗表示 |

## 9. リリース判定

初期リリースに進める条件:

- Microsoft Entra ID / Easy Auth が有効で、demo認証が無効化されている。
- 他ユーザー/別tenant jobアクセスが拒否される。
- 80分音声3本で標準経路が完了する。
- schema validation成功率が99%以上。
- 音声本文・transcript全文・minutes全文・SAS・token/keyがログに出ていない。
- 失敗時のユーザー向けエラーが理解できる。
- speaker mappingを手動で更新できる。
- direct generation、fallback、retry/backoff、polling backoffの性能期待値を満たす。

## 10. GitHub Actions検証マトリクス

### 10.1 PR CI

PR CIはAzureへログインせず、ソース、スキーマ、ビルド可能性を検証する。GitHub Actionsでは `ubuntu-latest` を既定にし、パスはLinux形式で記述する。

| Job | Runtime | Cache | Commands | 備考 |
|---|---|---|---|---|
| Backend | Python 3.13 exactly + uv | `backend/uv.lock` | `cd backend`; `uv sync --frozen`; `uv run ruff check .`; `uv run mypy .`; `uv run pytest --quiet`; `uv run python ../scripts/validate_specs.py` | Structured outputs / JSON Schema / OpenAPIの回帰を含める |
| Frontend | Node 20 | `frontend/package-lock.json` | `cd frontend`; `npm ci`; `npm run typecheck`; `npm test`; `npm run build` | lockfile前提。`npm install` ではなく `npm ci` |
| Infra | Azure CLI / Bicep | なし | `az bicep build --file infra/main.bicep` | OIDC変数がある内部PRでは `azd provision --preview --no-prompt` または `az deployment sub what-if/validate` も可 |
| Security | Python 3.13 / Node 20 | 各lockfile | gitleaksまたはsecret scanning、CodeQL、`pip-audit`、`npm audit` | CodeQL upload jobは必要に応じて `security-events: write` を付与 |

PR workflowのconcurrencyは `${{ github.workflow }}-${{ github.ref }}` を使い、`cancel-in-progress: true` にする。

### 10.2 dev deploy

現行のdev deploy workflowは手動 `workflow_dispatch` のみで、既定は `dry_run=true`。OIDC/RBAC、GitHub Environment、Bicepのservice principal role assignment caveatを解消するまで、`main` pushからの自動deployは有効化しない。

1. GitHub Environment `dev` を使い、OIDC subjectを `repo:<ORG>/<REPO>:environment:dev` に固定する。
2. deploy job permissionsは `contents: read` と `id-token: write` のみにする。
3. `azure/login` でOIDCログインする。
4. `AZURE_SUBSCRIPTION_ID`、`AZURE_LOCATION`、`AZURE_ENV_NAME=dev`、`AZURE_PRINCIPAL_ID` を設定する。`AZURE_PRINCIPAL_ID` はservice principalのobject IDでありclient IDではない。
5. `dry_run=false` の場合だけ `azd provision --no-prompt`、`azd deploy backend`、`azd deploy frontend` を実行する。

`azure.yaml` のbackend `prepackage` hookはroot `specs/` をbackend packageへ一時コピーする。schema filesをFunctions packageに含めるため、このhookをCI/CDでも保持する。AZD deploy runnerではPythonがPATHにあることを事前条件にする。

deploy/provision workflowのconcurrencyはenvironment単位にし、`cancel-in-progress: false` にする。

### 10.3 prod deploy

prod deployは手動 `workflow_dispatch` のみとし、GitHub Environment `prod` のrequired reviewers、保護ブランチ/タグ、OIDC subject `repo:<ORG>/<REPO>:environment:prod` を必須にする。

prod deploy前に次をassertionとして失敗させる。

- `MEETING_MINUTES_AUTH_MODE` が `demo` ではない。
- Frontend/BackendでMicrosoft Entra ID / Easy Authが有効。
- anonymous direct API callが業務APIを実行できない。
- 他ユーザー/別tenant jobアクセス拒否テストが成功している。

2026-06-01時点のdev MVPは `MEETING_MINUTES_AUTH_MODE=demo` のため、prod deployはブロック状態として扱う。
