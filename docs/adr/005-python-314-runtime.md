# ADR-005: Python 3.14 をバックエンド既定runtimeにする

日付: 2026-06-01

## 状態

ADR-006により置換

## 文脈

当初ユーザー要望として、バックエンドは Python 3.14 を使う案を検討した。Azure Functions は2026-06-01時点で Python 3.14 を Preview として扱う。Flex Consumption plan では Python 3.14 の remote build support がまだ利用できず、Linux Consumption plan は Python 3.12 が最後のPython versionになる。

その後、実装リスクを踏まえてユーザーが Python 3.13 採用を了承したため、このADRは `ADR-006: Python 3.13 をバックエンド既定runtimeにする` により置換する。

## 決定

バックエンドの既定runtimeを Python 3.14 にする案を採用候補とした。`pyproject.toml` の `requires-python` は `>=3.14,<3.15` とする想定だった。

Python 3.14対応のため、Linux Consumption plan は使わない。Phase 0で、Functions Premium、Flex Consumptionへのビルド済み成果物デプロイ、またはコンテナー化のいずれかを選び、Python 3.14でAzure Functionsと主要依存が解決・起動できることを確認してからAPI実装へ進む。

## 理由

- ユーザー指定を実装の前提として明確化する。
- Python 3.14 Preview制約を文書化し、実装途中で3.13などへ暗黙に下げることを防ぐ。
- remote buildやLinux Consumption planに依存したデプロイ失敗を早期に発見する。

## 結果

- 最新Pythonを前提に開発できる。
- Azure Functions側のPreview制約とSDK対応状況により、ホスティング方式の選択がPhase 0の必須確認になる。
- 主要依存が Python 3.14 に未対応の場合、runtime downgradeではなく、代替ホスティング方式またはADR更新を提案して承認を得る。

現在の採用runtimeは ADR-006 の Python 3.13 とする。

## Phase 0で確認すること

- `azure-functions`
- `azure-functions-durable`
- `azure-cosmos`
- `azure-storage-blob`
- `azure-identity`
- `openai`
- `pydantic`
- HTTP client

上記が Python 3.14 で解決できることを確認する。確認結果は実装PRまたは作業報告に残す。
