# Task 06: Implement frontend MVP

React + TypeScript で、音声アップロードから議事録表示までの最小UIを実装してください。

## 参照する仕様

- `docs/03-api-spec.md`
- `docs/01-requirements.md`
- `.github/instructions/frontend-typescript.instructions.md`

## 画面

1. Upload page
2. Job progress page
3. Transcript page
4. Speaker mapping panel
5. Minutes page

## 実装要件

- ファイルサイズと拡張子を事前チェックする。
- 可能ならブラウザで音声長を取得する。
- `POST /api/jobs` で uploadUrl を取得する。
- Blobへ直接アップロードし、進捗を表示する。
- upload完了後に `upload-complete` を呼ぶ。
- `GET /api/jobs/{jobId}` を2〜5秒間隔でポーリングする。
- `TRANSCRIPT_READY` 以降は transcript を表示する。
- `DONE` 以降は minutes を表示する。
- speaker mappingを更新できる。

## 注意

- SAS URLをconsole.logしない。
- ユーザー向け文言は日本語。
- API型はOpenAPIと矛盾しないようにする。
