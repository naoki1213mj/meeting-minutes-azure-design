# ADR-004: 議事録生成は transcript チャンク単位で並列化する

日付: 2026-05-29

## 状態

ADR-007により本線からは置き換え。chunk summary方式は自動fallbackとして保持。

## 文脈

80分の transcript を一括でLLMに投入することも可能だが、コスト、レイテンシ、再試行、根拠追跡の観点で運用しづらい。

## 決定

文字起こし後の normalized transcript を5〜10分相当の論理チャンクに分割し、chunk summary を並列生成する。最後に全chunk summaryを統合して final minutes を生成する。

## 理由

- 音声チャンク化と違い、speaker ID の整合性を壊さない。
- LLM処理を並列化できる。
- 失敗時にチャンク単位で再実行できる。
- timestamp根拠を保持しやすい。

## 結果

- chunk overlap を入れる場合、final mergeで重複除去が必要になる。
- OpenAIのTPM/RPMに合わせて並列度制御が必要になる。
- final merge の品質が議事録全体品質に影響する。

## 代替案

### transcript 全文一括投入

初期PoCの比較対象としては可。ただし運用では並列・再試行しにくい。

### LLMにMarkdownを直接生成させる

不採用。構造化後にアプリコードでMarkdown生成する。
