---
applyTo: "frontend/**/*.{ts,tsx}"
---

# Frontend TypeScript instructions

- TypeScript strict mode を前提にする。
- React function component を使う。
- API型は OpenAPI から生成するか、`specs/openapi.yaml` と整合する型を定義する。
- ファイルサイズ、拡張子、可能なら音声長をアップロード前にチェックする。
- Blobへの直接アップロードでは進捗を表示する。
- job status は2〜5秒間隔でポーリングする。将来 SignalR に差し替えやすくする。
- speaker mapping UIでは、各speakerの代表発話を表示してから表示名を入力させる。
- ユーザー向け文言は日本語にする。
- SAS URLをコンソールログに出さない。
