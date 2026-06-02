# Security Policy

## サポート状態

| 対象 | 状態 |
|---|---|
| `main` branch | dev MVP としてメンテナンス |
| Production deployment | Microsoft Entra ID / Easy Auth とユーザー単位認可が完了するまで未サポート |
| Demo auth deployment | ローカル・開発検証のみ |

このリポジトリは現在 dev MVP です。`MEETING_MINUTES_AUTH_MODE=demo` が残っている環境を、本番データや広範な利用に使わないでください。

## 脆弱性の報告

脆弱性を見つけた場合は、公開 Issue ではなく GitHub の private vulnerability reporting / Security Advisories を使って報告してください。リポジトリ側で private reporting が有効化されていない場合は、メンテナーが指定する非公開連絡経路を使ってください。

> 公開前チェック: メンテナーは、公開リポジトリで private vulnerability reporting または専用の非公開連絡先を設定してください。

報告には次を含めてください。

- 影響を受けるコンポーネント。
- 再現手順または検証観点。
- 期待される影響範囲。
- 可能であれば緩和策の提案。

報告に次を含めないでください。

- 音声本文、transcript 全文、議事録全文。
- SAS URL 全文、アクセストークン、API key、Storage account key。
- 実在する subscription ID、tenant ID、resource group、endpoint URL。
- 顧客名、個人情報、社外秘情報。

## 顧客デモのアクセス制御（共有キー方式）

顧客デモ用に、簡易な共有キー（合言葉）でアプリ全体をゲートできます。これは個人単位の認証ではなく、URL を知られても合言葉なしでは利用・攻撃できないようにするためのものです。

- フロントエンド（App Service / Express）が `/login` で合言葉を検証し、署名付き httpOnly Cookie でセッションを張ります。
- フロントエンドは `/api/*` を Function App へリバースプロキシし、サーバー側で別の秘密値（`MEETING_MINUTES_PROXY_SECRET`）を注入します。これにより Function App URL の直叩きを防ぎます。
- 顧客が入力する合言葉（`DEMO_ACCESS_KEY`）と、プロキシ用の秘密値（`MEETING_MINUTES_PROXY_SECRET`）は必ず別の値にします。後者はブラウザに送られません。
- `DEMO_ACCESS_KEY` は十分長いランダム値にします（例: `openssl rand -base64 24`）。短い合言葉はオンライン総当たりに弱くなります。
- これらの秘密値はコミットせず、デプロイ時の環境変数（`AZURE_DEMO_ACCESS_KEY` / `AZURE_PROXY_SECRET`）として与えます。
- Azure 上でキーが未設定の場合はフェイルクローズ（フロントは 503、バックエンドは 503/401）になります。
- この方式はデモ用の簡易ゲートであり、Entra ID / Easy Auth とユーザー単位認可の代替ではありません。

## セキュリティ設計の原則

- Microsoft Entra ID と managed identity を優先します。
- Storage account key を使った SAS は新規実装しません。User Delegation SAS を使います。
- API エラーはユーザー向け message と内部 details を分けます。
- 音声、transcript、議事録、SAS、token、key をログに出しません。
- speaker ID から実名を自動推定しません。
- 本番化前に、匿名アクセス拒否、他ユーザー job アクセス拒否、tenant 境界のテストを必須にします。
