# ADR-008: public ingest と private artifacts のStorage分離

## Status

Accepted

## Context

Minutes Studio の現行dev MVPは、ブラウザ直接アップロード、Azure Speech in Foundry Tools Fast Transcription の `audioUrl`、Content Understanding のURL参照Analyze APIを使う。このため、AIサービスがBlob URLへ到達できる public ingest 経路が必要になる。

一方で、transcript、minutes、visual context、Cosmos DB上のjob metadataは、ユーザー成果物または機密性の高いmetadataである。過去にStorage/Cosmosの `publicNetworkAccess` がIaC外で `Disabled` へドリフトし、job作成やCU処理が停止した。単にpublicへ戻すだけでは、成果物とmetadataがpublic data planeに残り続ける。

## Decision

中期対策として、Storageとネットワークを次のように分離する。

| 領域 | 方針 |
|---|---|
| Ingest Storage | public endpointを維持する。raw upload、Speech/CUが取得するBlob、標準経路の前処理済みFLACだけを置く |
| Artifact Storage | 別Storage accountに分離し、Private Endpoint + Private DNSでFunctionsからだけアクセスする |
| Cosmos DB | Private Endpoint + Private DNSを追加し、疎通確認後にpublic network accessを無効化する |
| Functions | Premium EP1のままVNet Integrationを追加する |
| AI Services | この段階ではprivate化しない |

Artifact とは、raw transcript response、normalized transcript、chunk、minutes JSON/Markdown、visual contextなど、ユーザーへBlob URLを直接公開しない処理成果物を指す。標準経路のm4a/mp4前処理で生成するFLACはSpeechが読むため、Artifact StorageではなくIngest Storageへ保存する。

Cosmos DBのpublic access無効化は、VNet Integration、Private Endpoint、Private DNSの到達性を確認した後の別デプロイで行う。単一デプロイで閉じると、FunctionsがCosmosへ到達できずジョブ処理が停止するリスクがある。

## Consequences

- transcript、minutes、visual contextをpublic data planeから分離できる。
- Cosmos DB metadataをFunctions private pathへ寄せられる。
- Ingest Storageのpublic endpointは残るため、完全閉域化ではない。残存リスクは、匿名公開無効、Shared Key無効、User Delegation SAS、短TTL、限定CORS、保存データ最小化で抑える。
- Backendはingest用SAS/storeとartifact用storeを分ける必要がある。
- 既存jobが旧Storage URLを参照しているため、読み取りfallbackまたは移行が必要になる。
- AzureWebJobsStorageの完全private化はPhase 1範囲外にする。必要な場合はBlob/Queue/Table/File Private EndpointとFunctions runtime検証を別ADRで扱う。

## Alternatives considered

1. **現行の単一public Storage/Cosmosを維持する。** デモの単純さは保てるが、成果物とmetadataのpublic data plane露出が残る。
2. **全Storageをprivate化する。** Speech/CUのURL fetch制約とブラウザ直接アップロード要件に合わず、現行経路を壊す。
3. **WorkerがBlobを読み、AI APIへinline送信する。** 完全private化に近づくが、大容量音声/動画ではサイズ制限、二重転送、処理時間、コストが悪化する。
