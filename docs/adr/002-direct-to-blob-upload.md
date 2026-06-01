# ADR-002: ブラウザからBlob Storageへ直接アップロードする

日付: 2026-05-29

## 状態

採用

## 文脈

80分音声はファイルサイズが大きくなりやすい。APIサーバー経由で受け取ると、ユーザーからAPI、APIからBlobの二重転送になる。

## 決定

ユーザーのブラウザは、APIから発行された短時間の User Delegation SAS を使い、Blob Storage へ直接アップロードする。

## 理由

- 大容量ファイルの二重転送を避けられる。
- APIの負荷とタイムアウトリスクを下げられる。
- Microsoft Entra ID による User Delegation SAS は Storage account key によるSASより安全性が高い。

## 結果

- APIはジョブ作成とSAS発行に集中する。
- ブラウザ実装にアップロード進捗管理が必要になる。
- SAS漏えい対策として、TTL短縮・最小権限・HTTPSを必須にする。

## 代替案

### APIサーバー経由アップロード

不採用。二重転送になり、レイテンシとコストが増える。

### Azure Storage SDK + Entra ID をブラウザで直接利用

将来検討。初期実装ではSASのほうが実装しやすい。
