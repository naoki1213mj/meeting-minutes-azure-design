# ADR-003: 長時間処理は Durable Functions の非同期ワークフローにする

日付: 2026-05-29

## 状態

採用

## 文脈

80分音声の文字起こしと議事録生成は、HTTPリクエスト内で完了する保証がない。Azure Functions のHTTP応答には230秒の上限がある。

## 決定

`upload-complete` API は Durable Functions orchestration を開始し、`202 Accepted` を返す。UIはjob status endpointをポーリングする。

## 理由

- 長時間処理の状態管理、checkpoint、retry、recoveryをDurable Functionsに任せられる。
- HTTP応答タイムアウトを避けられる。
- custom status により進捗表示しやすい。

## 結果

- UIは非同期ジョブとして扱う必要がある。
- Activityの冪等性設計が必要になる。
- Orchestrator内でI/Oをしないルールを守る必要がある。

## 代替案

### HTTP同期応答

不採用。230秒制約に当たりやすい。

### Azure Container Appsの単一Worker

一部処理には使えるが、状態管理を自作する必要があるため初期主経路では不採用。
