---
applyTo: "infra/**/*.bicep,infra/**/*.json,azure.yaml"
---

# Infrastructure instructions

- インフラはBicepを優先する。
- managed identity を使う。
- Storage account keyをアプリ設定へ出さない。
- Blob Storage、Cosmos DB、Function App、Application Insights、Speech、Azure OpenAI in Microsoft Foundry Models を分離して定義する。
- RBACは最小権限にする。
- 本番相当では public network access と Private Endpoint の要件をパラメーター化する。
- リソース名は環境名を含める。
- タグに `app`, `env`, `owner` を入れる。
