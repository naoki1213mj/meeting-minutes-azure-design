# Contributing

Minutes Studio へのコントリビュートありがとうございます。このリポジトリは日本語のユーザー向けドキュメントを基本とし、コード・設定・コメントは必要に応じて英語も使います。

## 重要な前提

- 現在は dev MVP です。Microsoft Entra ID / Easy Auth とユーザー単位認可が完了するまで production-ready ではありません。
- 初期実装の本線は、全体音声を Azure Speech in Foundry Tools Fast Transcription に 1 回だけ渡し、diarization を有効にする方式です。
- 音声チャンクごとの並列文字起こしは初期実装に入れません。議事録生成だけを transcript チャンクで並列化します。
- Markdown は LLM に直接書かせず、minutes JSON からコードで生成します。

## 開発環境

前提ツール:

- Python 3.13
- uv
- Node.js 20
- Azure CLI
- Azure Developer CLI (`azd`)

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

インフラ:

```powershell
az bicep build --file infra\main.bicep
```

## Pull Request の方針

1. 変更範囲を最小化してください。
2. `docs/` と `specs/` に矛盾しないことを確認してください。
3. API や schema を変える場合は、OpenAPI / JSON Schema / テストを一緒に更新してください。
4. 実行可能な最小の test / lint / typecheck を実行し、結果を PR に記載してください。
5. 実行できない検証がある場合は、理由と代替確認を記載してください。

## セキュリティと公開安全性

Issue、PR、ログ、スクリーンショットには次を含めないでください。

- 音声本文、transcript 全文、議事録全文
- SAS URL 全文、アクセストークン、API key、Storage account key
- 実在する subscription ID、tenant ID、resource group、storage account、endpoint URL
- 個人情報、顧客名、社外秘情報

例や手順には `<subscription-id>`、`<tenant-id>`、`<resource-group>`、`<function-app-name>` のような placeholder を使ってください。

## Issue の書き方

- バグ報告は再現手順、期待結果、実際の結果、影響範囲を書いてください。
- 実データは添付しないでください。必要なら匿名化した最小例にしてください。
- セキュリティ脆弱性は公開 Issue に書かず、`SECURITY.md` の手順に従ってください。
