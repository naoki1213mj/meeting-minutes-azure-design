# 10. 公式リファレンス

確認日: 2026-06-01

この文書は、設計判断に使った公式情報をまとめる。URLは確認日時点のもの。

## 1. Azure Speech Fast Transcription

URL: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/fast-transcription-create

確認した要点:

- Fast Transcription は、録音済み音声の transcript を同期的に、リアルタイムより速く返す用途向け。
- 会議メモ用途が明記されている。
- 入力音声は5時間未満、500MB未満。
- 長い音声では public URL からのアップロードが推奨されている。
- `locales` を指定すると、精度向上とレイテンシ低減に役立つ。
- diarization は会話内の異なる話者を分離し、phraseごとに `speaker` を含める。
- 既定では複数チャネルを1つにマージして文字起こしする。
- diarization有効時に stereo の `channels: [0,1]` は指定しない。
- retry は、429, 500, 502, 503, 504, network errors を対象に最大5回程度、指数バックオフが推奨されている。

## 2. Azure Speech quotas and limits

URL: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-services-quotas-and-limits

確認した要点:

- Fast Transcription の音声入力ファイルサイズは500MB未満。
- Fast Transcription の音声長は5時間未満。diarization 有効時は2時間未満。
- Fast Transcription の最大リクエスト数は Standard S0 で600 requests/min。
- LLM Speechも500MB未満、5時間未満。diarization 有効時は2時間未満。
- Batch Transcription は1GBまで、diarization有効時は240分まで。

## 3. Speech to Text REST API 2025-10-15

URLs:

- https://learn.microsoft.com/ja-jp/azure/ai-services/speech-service/migrate-2025-10-15
- https://learn.microsoft.com/en-us/rest/api/speechtotext/transcriptions/transcribe?view=rest-speechtotext-2025-10-15

確認した要点:

- Speech to Text REST API `2025-10-15` は、一般提供されている最新バージョン。
- `v3.0`, `v3.1`, `v3.2` 系は2026年3月31日に廃止済み。
- Fast Transcription のエンドポイントは `/speechtotext/transcriptions:transcribe?api-version=2025-10-15`。
- 公式例は inline `audio` を示すが、長い音声では `definition.audioUrl` を使う方針にする。

補足:

- REST APIリファレンスでは、inline `audio` の formData は2時間未満・250MB未満の制限が示されている。80分・大きめファイルの本番経路では `audioUrl` を使い、inline uploadは小さい開発・検証用に限定する。

## 4. Batch Transcription

URLs:

- https://learn.microsoft.com/en-us/azure/ai-services/speech-service/batch-transcription
- https://learn.microsoft.com/en-us/azure/ai-services/speech-service/batch-transcription-create
- https://learn.microsoft.com/en-us/azure/ai-services/speech-service/batch-transcription-get

確認した要点:

- Batch Transcription はベストエフォートでスケジュールされる。
- ピーク時はジョブ開始まで最大30分、完了まで最大24時間かかる可能性がある。
- 即時性を重視する今回の主経路にはしない。
- REST API は `/speechtotext/transcriptions:submit?api-version=2024-11-15` を使う。Speech CLI の `v3.2` はCLI向け互換経路であり、アプリ実装では使わない。
- diarization は `properties.diarization.enabled=true` と `maxSpeakers` で有効化する。`channels` は指定しない。
- 結果一覧では `kind: "Transcription"` の `links.contentUrl` だけを取得し、`TranscriptionReport` を正規化対象にしない。

## 5. LLM Speech

URL: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/llm-speech

確認した要点:

- LLM Speech は Microsoft Foundry のAPI。
- LLMが音声モデルを補強し、品質向上、文脈理解、多言語対応、prompt-tuning を提供する。
- 音声は inline upload または public `audioUrl` で渡せる。
- 長い音声では public URL からのアップロードが推奨されている。
- keyless authentication が推奨されている。
- ただし preview 扱いなので、初期本線は Fast Transcription とする。

## 6. MAI-Transcribe-1

URL: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/mai-transcribe

確認した要点:

- MAI-Transcribe-1 は LLM Speech API で利用できる。
- diarization はサポートされない。
- prompt-tuning はサポートされない。
- 今回の主経路には使わない。

## 7. Azure OpenAI in Microsoft Foundry Models v1 API

URL: https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle

確認した要点:

- v1 API は認証を簡素化し、dated `api-version` パラメーターを不要にする。
- Pythonでは `openai.OpenAI` client を使い、`base_url` に `/openai/v1/` を付ける。
- Microsoft Entra ID 認証では `DefaultAzureCredential` と token provider を使える。
- 新規実装では `AZURE_OPENAI_API_VERSION` を増やさず、v1 API に寄せる。

## 8. Azure OpenAI Structured outputs

URL: https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs

確認した要点:

- Structured outputs は、推論API呼び出しで指定したJSON Schemaにモデル出力を従わせる機能。
- JSON mode は有効なJSONを保証するが、指定スキーマへの厳密な準拠までは保証しない。
- Structured outputs では、すべてのobjectで `additionalProperties: false` を指定する。
- すべてのフィールドを required にする。任意項目は `type: ["string", "null"]` のように null union で表す。
- `format`, `pattern`, `minItems`, `maxItems` などのtype-specific keywordsは使えない。
- この制約のため、LLM呼び出し用schemaとアプリ保存用schemaを分ける。

## 9. Microsoft Foundry model choice guide and model retirement

URLs:

- https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/model-choice-guide
- https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure
- https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule

確認した要点:

- GPT-4.1 は高速・高スループット・低レイテンシ用途や軽量要約に向く。
- GPT-5 系は複雑な推論や高品質な分析に向くが、モデルによってはレイテンシやパラメーター制約が変わる。
- GPT-5.4 mini / GPT-5.4 は議事録生成の第一候補にする。ただし、Structured outputs対応、入出力トークン上限、利用可能なデプロイ種別、quota、データ処理場所は対象サブスクリプションで確認してから確定する。
- 2026-05-31時点の model retirement schedule では、gpt-4.1 / gpt-4.1-mini / gpt-4.1-nano は 2026-10-14 に retirement 予定。
- そのため、GPT-4.1系は速度・コスト・Regional/Data residency比較候補に残し、PoC結果で本番既定モデルをADR化する。

## 10. Azure OpenAI quotas and limits

URL: https://learn.microsoft.com/en-us/azure/foundry/openai/quotas-limits

確認した要点:

- TPM/RPM制限はtenant単位ではない。
- サブスクリプション、リージョン、モデル、デプロイ種別ごとに定義される。
- chunk summary の並列度はこの制限を踏まえて調整する。
- 429が増える場合は、急な負荷増加を避け、並列度を下げる。

## 11. Azure Functions HTTP timeout

URL: https://learn.microsoft.com/en-us/azure/azure-functions/functions-scale

確認した要点:

- Azure Functions の HTTP triggered function は、function timeout設定にかかわらず、応答に使える最大時間が230秒。
- 長時間処理では Durable Functions async pattern または即時応答が推奨されている。

## 12. Durable Functions

URLs:

- https://learn.microsoft.com/en-us/azure/azure-functions/durable-functions/durable-functions-overview
- https://learn.microsoft.com/en-us/azure/azure-functions/durable-functions/durable-functions-http-features
- https://learn.microsoft.com/en-us/azure/azure-functions/durable-functions/durable-functions-diagnostics
- https://learn.microsoft.com/en-us/azure/durable-task/common/durable-task-custom-orchestration-status

確認した要点:

- Durable Functions は serverless な stateful workflow を実装できる。
- 長時間HTTP API向けに `202 Accepted` と status polling のパターンをサポートする。
- runtime が state, checkpoints, retries, recovery を管理する。
- custom orchestration status により、クライアントへ進捗を見せられる。
- Application Insights でライフサイクルイベントやトレースを確認できる。

## 13. User Delegation SAS and direct browser upload

URLs:

- https://learn.microsoft.com/en-us/rest/api/storageservices/create-user-delegation-sas
- https://learn.microsoft.com/en-us/azure/developer/javascript/tutorial/browser-file-upload-azure-storage-blob
- https://learn.microsoft.com/en-us/azure/storage/common/storage-sas-overview

確認した要点:

- Microsoft は可能な場合、Microsoft Entra ID と managed identities で Blob/Queue/Table へアクセスすることを推奨している。
- SASが必要な場合、Storage account key ではなく Microsoft Entra credentials による User Delegation SAS が推奨されている。
- ブラウザからBlobへ直接アップロードする Valet Key pattern の公式チュートリアルがある。

## 14. Content Understanding

URLs:

- https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/audio/overview
- https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/service-limits

確認した要点:

- Content Understanding は conversational audio を WebVTT transcript などに変換し、field extraction も扱える。
- 300MB以下または2時間以下では、transcription time が大きく短縮される旨の記述がある。
- Audioは300MB/2時間以下が高速処理の目安で、最大1GB/4時間まで対応する。
- VideoはURL参照のAnalyze APIで最大4GB/2時間。direct binary uploadは200MB/30分。
- Videoでは `transcriptPhrases`、key frames、camera shots、fields、markdownを取得できる。`returnDetails=true` が必要な詳細項目がある。
- ただし今回の初期本線は、制御性を優先して Fast Transcription + Azure OpenAI の明示的なパイプラインにする。
- 将来比較する場合は、2025-11-01 GA API など現行APIを確認する。

## 15. Azure Container Apps Jobs

URL: https://learn.microsoft.com/en-us/azure/container-apps/jobs

確認した要点:

- Container Apps Jobs は、有限時間で実行して停止するコンテナー化タスク向け。
- データ処理、機械学習、オンデマンド処理などに向く。
- 音声の ffprobe/ffmpeg 前処理が必要になった場合の候補。

## 16. Azure SignalR Service

URL: https://learn.microsoft.com/en-us/azure/azure-signalr/signalr-overview

確認した要点:

- Azure SignalR Service はサーバーから接続中クライアントへリアルタイム更新をpushできる。
- クライアントのポーリング削減に使える。
- 初期実装では任意。PoC後に必要なら追加する。

## 17. Application Insights

URL: https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview

確認した要点:

- Application Insights はアプリケーションの可観測性機能を提供する。
- Azure Monitor と OpenTelemetry ベースの収集に対応する。
- jobId単位のカスタムメトリックと依存関係トレースに使う。

## 18. Azure Functions Python runtime support

URL: https://learn.microsoft.com/azure/azure-functions/functions-versions#languages

確認した要点:

- Azure Functions runtime は Python/JavaScript/TypeScript/Java/PowerShell では 4.x のみがサポート対象。
- 2026-06-01時点で Python 3.14 は Preview、Python 3.13 と 3.12 は GA。
- 本PJは Python 3.13 を既定runtimeにする。
- Python 3.14 のGA時期とサポート終了日は未定。
- Flex Consumption plan で Python 3.14 の remote build support はまだ利用できない。
- Python 3.12 が Linux Consumption plan でサポートされる最後の Python version。新しいPython versionを使う場合、Linux Consumption plan は避ける。

## 19. GitHub Copilot CLI custom instructions

URL: https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions

確認した要点:

- Copilot CLI は `.github/copilot-instructions.md` の repository-wide instruction をサポートする。
- `.github/instructions/**/*.instructions.md` の path-specific instruction をサポートする。
- `AGENTS.md` もサポートされ、root の `AGENTS.md` は primary instruction として扱われる。
- instruction同士が矛盾すると挙動が不安定になりうるため、重複指示は同じ内容に揃える。
