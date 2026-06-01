# Task 02: Implement backend API skeleton

Azure Functions PythonでAPIの骨格を実装してください。

## 参照する仕様

- `docs/03-api-spec.md`
- `specs/openapi.yaml`
- `docs/04-data-model.md`
- `AGENTS.md`

## 実装対象

- `POST /api/jobs`
- `POST /api/jobs/{jobId}/upload-complete`
- `GET /api/jobs/{jobId}`

## 必須実装

1. Pydanticモデルを作成する。
2. JobRepository interface を作成する。
3. BlobSasIssuer interface を作成する。
4. Cosmos DB/Blobの本実装は後で差し替えられるようにする。
5. ローカルテスト用のインメモリ実装を作る。
6. エラー形式を `docs/03-api-spec.md` に合わせる。
7. すべてのAPIに単体テストを追加する。

## 注意

- Azure Functions関連依存を追加する前に、Python 3.13で `azure-functions` と必要な周辺依存が解決できることを確認してください。
- SAS URL全文をログに出さない。
- `upload-complete` は冪等にしてください。
- Orchestrator開始処理は、このタスクでは interface または stub で構いません。
