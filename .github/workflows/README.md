# GitHub Actions deploy workflows

このディレクトリの deploy workflow は、OIDC/RBAC と本番化ゲートが整うまで手動・guarded 実行だけにしています。

## `deploy-dev.yml`

- 手動 `workflow_dispatch` のみです。自動 `push` deploy はありません。
- GitHub Environment は `dev` です。Environment deployment branch rule も `main` に固定してください。
- Environment variables:
  - `AZURE_CLIENT_ID`
  - `AZURE_TENANT_ID`
  - `AZURE_SUBSCRIPTION_ID`
  - `AZURE_LOCATION`
  - `AZURE_ENV_NAME=dev`
  - `AZURE_PRINCIPAL_ID`（client ID ではなく service principal object ID）
- OIDC subject は `repo:<ORG>/<REPO>:environment:dev` に固定してください。
- 現行 IaC は role assignment を作るため、deploy identity には必要スコープで `Contributor` に加えて `User Access Administrator`、`Role Based Access Control Administrator`、または `Owner` が必要です。
- 現行 `infra/app.bicep` の `developerDurableTaskRole` は `principalType: 'User'` のため、service principal OIDC の実デプロイはブロックされます。Bicep修正またはbootstrap分離後に `dry_run=false` を使ってください。

## `deploy-prod.yml`

`MEETING_MINUTES_AUTH_MODE=demo` を本番で使わず、Microsoft Entra ID / Easy Auth とユーザー単位認可が有効になるまで常に失敗します。Azure login や deploy は実行しません。

## 禁止

publish profile、`AZURE_CREDENTIALS`、API key、Storage account key、SAS URL は使わないでください。
