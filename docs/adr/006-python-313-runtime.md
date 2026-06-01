# ADR-006: Python 3.13 をバックエンド既定runtimeにする

日付: 2026-06-01

## 状態

採用

## 文脈

当初は Python 3.14 を検討したが、2026-06-01時点で Azure Functions の Python 3.14 は Preview であり、Flex Consumption plan の remote build support も未対応だった。初期実装では Durable Functions、Azure SDK、Pydantic、OpenAI SDK などの依存解決とデプロイ安定性を優先する。

ユーザーは Python 3.13 採用を了承した。

## 決定

バックエンドの既定runtimeを Python 3.13 にする。`pyproject.toml` の `requires-python` は `>=3.13,<3.14` とする。Azure Functions runtime は v4 を使う。

## 理由

- Azure Functions の Python 3.13 はGAであり、Preview runtimeより実装・デプロイリスクが低い。
- Python 3.14 のPreview制約に引きずられず、Durable FunctionsとAzure SDKの実装検証を進めやすい。
- 将来 Python 3.14 がGAになった時点で、別ADRとしてアップグレード判断できる。

## 結果

- 初期実装は Python 3.13 に固定する。
- Python 3.14へ上げる場合は、Azure Functionsのサポート状況、ホスティング方式、remote build、依存ライブラリ対応を再確認し、ADRを追加または更新する。
- Phase 0で Python 3.13 による主要依存解決とローカルテスト実行を確認する。
