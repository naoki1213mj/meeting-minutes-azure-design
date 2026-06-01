# Task 01: Bootstrap repository

このリポジトリに、設計書に沿った最小構成を作ってください。

## 参照する仕様

- `README.md`
- `docs/00-design-summary.md`
- `docs/08-implementation-plan.md`
- `AGENTS.md`
- `.github/copilot-instructions.md`

## 作業内容

1. `backend/` を Python 3.13 + uv のプロジェクトとして作成してください。`pyproject.toml` の `requires-python` は `>=3.13,<3.14` にしてください。
2. `frontend/` を React + TypeScript + Vite のプロジェクトとして作成してください。
3. `infra/` を作り、Bicepファイルを置ける構成にしてください。
4. rootに `.gitignore` を追加してください。
5. backendに pytest, ruff, mypy を設定してください。
6. frontendに typecheck, test, build script を用意してください。
7. READMEにローカル開発コマンドを追記してください。

## 完了条件

- `cd backend && uv run pytest` が成功する。
- `cd backend && uv run ruff check .` が成功する。
- `cd frontend && npm run typecheck` が成功する。
- まだ実装が空でも、テストが1件以上ある。
- JSON Schema と OpenAPI の job status enum 整合性を検査するスクリプトまたはテストがある。

## 注意

- まだAzure接続実装は不要です。
- 仕様ファイルは変更しないでください。
- Python 3.13 は本PJの既定runtimeです。Python 3.14へ勝手に上げず、変更が必要な場合はADRを更新してください。
