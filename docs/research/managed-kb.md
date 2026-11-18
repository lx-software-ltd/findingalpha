# Research: Bedrock Managed Knowledge Base

**Status**: Done. Read on 17 November 2026 (Hong Kong).
**Zone**: green. This memo changes no product code. The milestone it
serves (M07) is red.

No AWS resource was created and no Bedrock API was called. The only AWS
calls were read-only S3 listings of the knowledge base bucket. Every
claim below comes from AWS documentation, the published API model, the
published CloudFormation schema, or the published price list. A claim
that only a deployed knowledge base can prove is marked **unverified**.

Book titles and evaluation questions stay out of this memo.

## Entry points

This is step M07-T01 of `docs/plans/07-knowledge-base.md`. The sources
read on the day:

- User guide:
  [Build a managed knowledge base](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-build-managed.html),
  [Prerequisites](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-prereqs.html),
  [Create](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html),
  [Service role](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-permissions.html),
  [Connect a data source](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-connect-ds.html),
  [Amazon S3 connector](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-ds-s3.html),
  [Customize ingestion](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-customize-ingestion.html),
  [Sync](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-sync.html),
  [Query and retrieve](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve.html),
  [Query configurations](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html),
  [Observability](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-observability.html),
  [Quotas](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-quotas.html),
  [Regions](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-regions.html),
  [Document formats](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-ds.html),
  [Document content](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-get-document-content.html).
- API reference:
  [CreateKnowledgeBase](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_CreateKnowledgeBase.html),
  [CreateDataSource](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_CreateDataSource.html),
  [StartIngestionJob](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_StartIngestionJob.html),
  [Retrieve](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_Retrieve.html),
  [RetrieveAndGenerate](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_RetrieveAndGenerate.html).
- [Service quotas for Amazon Bedrock](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)
  and the
  [IAM actions for Amazon Bedrock](https://docs.aws.amazon.com/service-authorization/latest/reference/list_bedrock.html).
- [Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/) and
  the price list file
  `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonKnowledgeBase/current/ap-southeast-1/index.json`
  (published 26 October 2026).
- CloudFormation: the resource schemas for `ap-southeast-1` in
  `https://schema.cloudformation.ap-southeast-1.amazonaws.com/CloudformationSchema.zip`
  (files dated 17 November 2026), the
  [template reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-bedrock-knowledgebase-managedknowledgebaseconfiguration.html),
  [coverage roadmap issue 2531](https://github.com/aws-cloudformation/cloudformation-coverage-roadmap/issues/2531),
  and [aws-cdk pull request 38275](https://github.com/aws/aws-cdk/pull/38275).
- The SDK model in botocore 1.44.3 (`bedrock-agent` 2023-06-05 and
  `bedrock-agent-runtime` 2023-07-26).
- The package `awslabs.bedrock-kb-retrieval-mcp-server` 1.1.2 from PyPI,
  read as source.

## Owners

M07. The CDK resources are M07-T02 (`backend/infrastructure/lib/knowledge-base.ts`,
red). Sync is M07-T03 (`backend/lambda/engine/kb_sync.py`). Retrieval is
M07-T04 (`backend/lambda/engine/kb_client.py`).

## Callers

None yet. `KbBucket` exists (`backend/infrastructure/lib/data.ts`). The
caps `KbMaxRawBytes` and `KbMaxRetrievalsPerMonth` are stack parameters
(`backend/infrastructure/params/production.json`). No code calls Bedrock.

## Existing abstractions

- `aws-cdk-lib` 2.277.0 is installed (`backend/infrastructure/package-lock.json`).
  Its `CfnKnowledgeBase` and `CfnDataSource` already carry the managed
  types.
- `AdminApiFn` and `EngineFn` run on the Python 3.12 runtime and are
  both built from `backend/lambda/engine`. When this memo was written
  that directory had no requirements, so both used the runtime's boto3.
  The pin in the table below replaces that copy in both functions.

## Answers

1. **Use `CfnKnowledgeBase`.** Issue 2531 is still open on GitHub, with
   no reply from AWS and no update since 27 June 2026 (UTC). The defect it
   reports is gone from the schema. The issue said `EmbeddingModelArn`
   was required by the schema and rejected by the service for
   `EmbeddingModelType: MANAGED`. Today:
   - The schema for `AWS::Bedrock::KnowledgeBase` published for
     `ap-southeast-1` has no required property inside
     `ManagedKnowledgeBaseConfiguration`.
   - The template reference lists `EmbeddingModelArn` as "Required: No".
   - aws-cdk pull request 38275, merged on 9 July 2026 (UTC), changed the
     property from required to optional. The installed 2.277.0 has
     `embeddingModelArn?: string`.
   - A probe stack built with the installed L1 classes (managed
     knowledge base, tags, one managed S3 data source with fixed-size
     chunking) synthesizes, and both resources pass the published
     schemas with zero errors. That request also passes botocore 1.44.3
     parameter validation. Neither check sees the service rule that
     rejected it on deploy.

   **The knowledge base resource is accepted.** The first deploy, on
   17 November 2026 (Hong Kong), created `TheoryKnowledgeBase`.
   `CreateDataSource` then rejected the data source: "A chunking
   strategy cannot be specified with a managed embedding model. Omit
   chunkingConfiguration to use the default." CloudFormation rolled the
   create back and deleted the knowledge base, the data source, the
   role and the alarm. `CfnKnowledgeBase` needs no custom resource.
   `AWS::Bedrock::DataSource` also supports the managed connector. The
   data source omits `vectorIngestionConfiguration`, because managed
   embedding rejects a chunking strategy and Smart Parsing is the
   documented default. Parsing was in that first request and the
   service never reached it.
2. **The four requests are in "Request shapes".** Each one passes the
   SDK's parameter validation against the botocore 1.44.3 model. The
   request the first deploy sent passes that check too, so validation
   does not catch the chunking rejection.
3. **Prices are unchanged.** Storage is 5.00 US dollars per GB-month of
   raw data and `Retrieve` is 1.00 per 1,000 calls, on the pricing page
   and in the `ap-southeast-1` price list (effective 1 October 2026).
   Parsing, managed embedding and managed reranking are free. Agentic
   retrieval is 4.00 per 1,000 calls plus 1.00 per 1,000 underlying
   `Retrieve` calls. See "Prices and monthly estimate".
4. **No model access is needed.** With managed embedding and managed
   reranking "no Bedrock model access is required"
   ([Prerequisites](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-prereqs.html)).
   Model access is needed only for a custom embedding model or a custom
   reranking model. The plan uses neither.
5. **The IAM actions are in "IAM actions".**

Two more questions came up while preparing the owner's files:

6. **Scanned books: AWS says yes, with no detail.** The overview page
   says Smart Parsing "auto-selects parsing strategy per document type
   including PDFs, PPTX, DOCX, documents with embedded visuals, audio,
   video, and scanned documents"
   ([Knowledge Bases](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)).
   No page names the mechanism, the setting that controls it, or the
   quality on mathematics. See "Scanned books".
7. **File size: the documentation gives three numbers.** The bucket
   meets the strictest one. See "File size".

## What the plan must change

These follow from the answers. Each is a correction to
`docs/plans/07-knowledge-base.md` for the owner to approve with T02.

| Plan text | Finding | Proposed change |
| --- | --- | --- |
| T02.3 "Data deletion policy: retain" | "For managed knowledge bases, the only supported option is DELETE, which is also the default" (CreateDataSource reference) | Use `DELETE`. Removal policy retain-except-on-create on the knowledge base only: a rolled-back create is deleted, and a knowledge base that exists is kept. Data sources are not retained. The PDFs in S3 stay the source of truth |
| T02.3 "fixed size, 800 tokens, 15% overlap" | The first deploy created the knowledge base, then `CreateDataSource` rejected `chunkingConfiguration` with managed embedding. Rollback deleted the new resources | **Decided** the same night: omit `vectorIngestionConfiguration`. The default is 300 tokens with 20% overlap. Smart Parsing stays the service default and is left out of the request |
| T02.3 data source on S3 | A managed knowledge base takes `type: MANAGED_KNOWLEDGE_BASE_CONNECTOR` with `connectorParameters`. The `s3Configuration` shape is for self-managed knowledge bases | Use the request in "Request shapes". One prefix per data source through `filterConfiguration.inclusionPrefixes` |
| T02.6 "`RawDataSize` above 1.5 GB" | The metric's unit is Gigabytes and its dimension is `KnowledgeBaseId` with the value `knowledge-base/<id>` (Observability page). The bucket holds 1.96 GB today | **Decided** on 17 November 2026 (Hong Kong): threshold 2.0 GB |
| T02.1 service role | Runtime metrics are published with the service role's credentials and need `cloudwatch:PutMetricData` limited to the namespace `AWS/Bedrock/KnowledgeBases` | Add that statement. Without it the metrics are silently missing |
| "Deleting more than 15% ... is blocked by default" | The threshold defaults to 15 when protection is enabled. The default status is undocumented. A sync over the threshold "skips its delete phase" and still adds and updates | Set `deletionProtectionStatus: ENABLED` and threshold 15 explicitly. The `blocked_deletion` status in `kb_sync` stays the gate that stops a sync |
| T03 "Failed documents are listed by key" | `GetIngestionJob` returns counts only (scanned, indexed, failed, skipped, deleted) | Read keys from `ListKnowledgeBaseDocuments` (status and S3 location per document). `EngineFn` then needs `bedrock:ListKnowledgeBaseDocuments`. Record `numberOfDocumentsSkipped` too |
| T04 `source_types` "when sidecars carry it" | Managed knowledge bases add reserved metadata with an underscore prefix, such as `_source_uri` and `_data_source_id` (Query configurations page). The AWS MCP server filters managed knowledge bases with `in` on `_data_source_id` | Filter on `_data_source_id` with the ids from `KB_DATA_SOURCE_IDS`. No sidecar is needed for this. **Unverified** until the first `Retrieve` |
| T04 client | `managedSearchConfiguration` needs botocore 1.43.64 or later. The version inside the Lambda runtime "depends on the runtime version and your AWS Region" (Lambda Python page) | **Decided** the same day, and tightened after review: pin `boto3==1.44.3` and `botocore==1.44.3` in `backend/lambda/engine/requirements.txt`. boto3 1.44.3 accepts any botocore from 1.44.3 up to 1.45, and the request shapes live in botocore. `AdminApiFn` and `EngineFn` are both built from that directory, so both bundle the pin |
| T07 profile actions | Server 1.1.2 calls `GetKnowledgeBase` for every knowledge base to read its ARN and type | Add `bedrock:GetKnowledgeBase`. Keep `bedrock:AgenticRetrieveStream` out, so the server's agentic tool is denied by IAM |
| Open question "budget alert on the Bedrock service" | Billing uses its own service, "Amazon Bedrock Managed Knowledge Base" (service code `AmazonKnowledgeBase`) | A budget filtered to Amazon Bedrock would miss this cost. Filter on the new service or on the tag `Project` |

## Recheck of the plan's verified list

| Line in the plan | Result | Source |
| --- | --- | --- |
| Available in `ap-southeast-1` | Confirmed | Regions page; the price list has `APS1-` usage types |
| Hybrid search always on | Confirmed. "Semantic-only search is not available" | Query and retrieve page |
| Embedding, reranking, parsing included and managed | Confirmed, each at 0 US dollars | Pricing page |
| 5 per GB-month, 1 per 1,000 `Retrieve` | Confirmed | Pricing page and price list |
| `Retrieve` takes `managedSearchConfiguration` | Confirmed | Retrieve reference; SDK model |
| No `overrideSearchType` | Confirmed. The SDK rejects it inside `managedSearchConfiguration` | SDK model |
| `startsWith` and `stringContains` unsupported | Confirmed. Use `equals`, `greaterThan`, `lessThan`, `in`, `notIn` | Query configurations page |
| `RetrieveAndGenerate` unsupported (non-goal) | Confirmed. "This API cannot be used with managed knowledge bases" | RetrieveAndGenerate reference |
| File limit 50 MB | Unclear. See "File size" | Three pages disagree |
| Types: PDF, Markdown, text, HTML, Word, Excel, CSV | Confirmed. The overview also names PPTX, and images, audio and video when media extraction is on | Document formats page |
| Sidecar `<file>.metadata.json`, at most 10 KB | Confirmed. The managed format is typed, see "Request shapes" | S3 connector page |
| Chunking fixed at creation | Partly. The guide says the strategy cannot be changed after connect, and CloudFormation replaces the data source on a change. With managed embedding the service rejects `chunkingConfiguration` itself. The first deploy returned that error and rolled back | Customize ingestion page; schema `createOnlyProperties`; deploy on 17 November 2026 (Hong Kong) |
| Default 300 tokens, 20% overlap; none; fixed size; no semantic | Partly. The guide lists default (300 tokens, 20% overlap), none, and fixed size, and semantic chunking is unsupported. The first deploy sent `FIXED_SIZE` at 800 tokens and 15% overlap, and the service rejected that request. `NONE` was not tried. The guide still lists fixed size and none | Customize ingestion page, read again on 18 November 2026 (Hong Kong); first deploy |
| Deleting more than 15% is blocked by default | Partly. See the table above | Connect a data source page |
| 200 data sources, 600 `Retrieve` a minute | Confirmed. Also 100 `Retrieve` a second per account, 50 concurrent ingestion jobs per knowledge base, 10,000 characters per query, 10 TB per knowledge base, 30 MB of extracted text per file | Quotas pages |
| Metric `RawDataSize` in `AWS/Bedrock/KnowledgeBases` | Confirmed. Unit Gigabytes, published after an ingestion job completes | Observability page |
| CloudFormation could not create it (issue 2531) | Changed. See answer 1 | Schema, template reference, CDK |
| MCP server supports managed, tag `mcp-multirag-kb=true` | Confirmed. 1.1.2 is still the latest (22 September 2026). It detects the type and sends `managedSearchConfiguration` | PyPI package source |

## Request shapes

### CreateKnowledgeBase

`PUT /knowledgebases/`, answers HTTP 202. The reference syntax for the
managed type:

```json
{
  "clientToken": "string",
  "description": "string",
  "name": "string",
  "roleArn": "string",
  "knowledgeBaseConfiguration": {
    "type": "MANAGED",
    "managedKnowledgeBaseConfiguration": {
      "embeddingModelType": "MANAGED | CUSTOM",
      "embeddingModelArn": "string",
      "embeddingModelConfiguration": { "bedrockEmbeddingModelConfiguration": {} },
      "serverSideEncryptionConfiguration": { "kmsKeyArn": "string" },
      "supplementalDataStorageConfiguration": { "storageLocations": [] }
    }
  },
  "tags": { "string": "string" }
}
```

"When using `MANAGED`, you must not specify `embeddingModelArn` or
`embeddingModelConfiguration`." There is no `storageConfiguration`. The
embedding type is permanent. Creation is asynchronous: poll
`GetKnowledgeBase` until `status` is `ACTIVE`.

The request for this project:

```json
{
  "name": "findingalpha-theory",
  "description": "Finance theory books and the system journal",
  "roleArn": "arn:aws:iam::<account>:role/<service role>",
  "knowledgeBaseConfiguration": {
    "type": "MANAGED",
    "managedKnowledgeBaseConfiguration": { "embeddingModelType": "MANAGED" }
  },
  "tags": { "mcp-multirag-kb": "true", "Project": "Finding Alpha" }
}
```

The same in CloudFormation, as the probe synthesized it:

```json
{
  "Type": "AWS::Bedrock::KnowledgeBase",
  "Properties": {
    "Name": "findingalpha-theory",
    "RoleArn": "arn:aws:iam::<account>:role/<service role>",
    "KnowledgeBaseConfiguration": {
      "Type": "MANAGED",
      "ManagedKnowledgeBaseConfiguration": { "EmbeddingModelType": "MANAGED" }
    },
    "Tags": { "mcp-multirag-kb": "true" }
  },
  "UpdateReplacePolicy": "Retain",
  "DeletionPolicy": "Retain"
}
```

### CreateDataSource

`PUT /knowledgebases/{knowledgeBaseId}/datasources/`. The reference
syntax for the managed connector:

```json
{
  "clientToken": "string",
  "name": "string",
  "description": "string",
  "dataDeletionPolicy": "DELETE",
  "dataSourceConfiguration": {
    "type": "MANAGED_KNOWLEDGE_BASE_CONNECTOR",
    "managedKnowledgeBaseConnectorConfiguration": {
      "connectorParameters": "JSON value",
      "deletionProtectionConfiguration": {
        "deletionProtectionStatus": "ENABLED | DISABLED",
        "deletionProtectionThreshold": 15
      },
      "mediaExtractionConfiguration": {
        "imageExtractionConfiguration": { "imageExtractionStatus": "ENABLED | DISABLED" },
        "audioExtractionConfiguration": { "audioExtractionStatus": "ENABLED | DISABLED" },
        "videoExtractionConfiguration": { "videoExtractionStatus": "ENABLED | DISABLED" }
      },
      "syncSchedule": {}
    }
  },
  "vectorIngestionConfiguration": {
    "parsingConfiguration": { "parsingStrategy": "SMART_PARSING" }
  }
}
```

The published shape can include `vectorIngestionConfiguration`. This
project leaves that property out. The notes below say why.

`connectorParameters` for S3, from the connector page:

```json
{
  "type": "S3",
  "version": "1",
  "connectionConfiguration": { "bucketName": "string", "bucketOwnerAccountId": "string" },
  "filterConfiguration": {
    "inclusionPrefixes": ["string"],
    "exclusionPrefixes": ["string"],
    "inclusionPatterns": ["regex"],
    "exclusionPatterns": ["regex"],
    "maxFileSizeInMegaBytes": "500"
  },
  "metadataFilesPrefix": "string",
  "aclEnabled": false
}
```

The request for the `theory` data source. The other two differ in
`name` and the prefix:

```json
{
  "knowledgeBaseId": "<knowledge base id>",
  "name": "theory",
  "dataDeletionPolicy": "DELETE",
  "dataSourceConfiguration": {
    "type": "MANAGED_KNOWLEDGE_BASE_CONNECTOR",
    "managedKnowledgeBaseConnectorConfiguration": {
      "connectorParameters": {
        "type": "S3",
        "version": "1",
        "connectionConfiguration": {
          "bucketName": "<knowledge base bucket>",
          "bucketOwnerAccountId": "<account>"
        },
        "filterConfiguration": {
          "inclusionPrefixes": ["theory/"],
          "maxFileSizeInMegaBytes": "50"
        }
      },
      "deletionProtectionConfiguration": {
        "deletionProtectionStatus": "ENABLED",
        "deletionProtectionThreshold": 15
      }
    }
  }
}
```

Notes:

- Creation is asynchronous. The status moves from `CREATING` to
  `AVAILABLE`.
- `maxTokens` accepts 1 to 8192 and `overlapPercentage` 1 to 99 where
  the service accepts a chunking strategy. The user guide shows
  `"chunkingStrategy": "DEFAULT"` for 300 tokens and 20% overlap, and
  it still lists fixed size and none for a managed knowledge base.
  The API reference, the SDK and the CloudFormation schema list
  `FIXED_SIZE`, `NONE`, `HIERARCHICAL` and `SEMANTIC`. The first deploy
  sent `FIXED_SIZE` at 800 tokens and 15% overlap. The service
  answered: "A chunking strategy cannot be specified with a managed
  embedding model. Omit chunkingConfiguration to use the default."
  `NONE` was not tried. This project omits `chunkingConfiguration`.
  That request passes botocore 1.44.3 validation and the CloudFormation
  schema, so those checks do not see this rule.
- This project also omits `parsingConfiguration`. Smart Parsing is the
  documented default. The first deploy failed on chunking before the
  service read the parsing setting.
- The template sets `maxFileSizeInMegaBytes` to `"50"`. The first
  deploy sent that value and failed on chunking before the service
  reported on the cap, so whether the service accepts `"50"` is still
  untested.
- `BEDROCK_FOUNDATION_MODEL` and `BEDROCK_DATA_AUTOMATION` parsing are
  unsupported for managed knowledge bases.
- With no `syncSchedule` the data source syncs only on
  `StartIngestionJob`. That matches `kb_sync_check`.
- In CloudFormation, `ConnectorParameters` is a free-form object. The
  CDK passes its keys through in lower camel case, as the service
  expects.
- A sidecar sits next to its document as
  `<file>.<extension>.metadata.json`. The managed format is typed:

  ```json
  {
    "metadataAttributes": {
      "source_type": { "value": { "type": "STRING", "stringValue": "theory" } },
      "year": { "value": { "type": "NUMBER", "numberValue": 2014 } }
    }
  }
  ```

### StartIngestionJob

`PUT /knowledgebases/{knowledgeBaseId}/datasources/{dataSourceId}/ingestionjobs/`,
answers HTTP 202. The whole body:

```json
{ "clientToken": "string", "description": "string" }
```

The response and `GetIngestionJob` return:

```json
{
  "ingestionJob": {
    "ingestionJobId": "string",
    "knowledgeBaseId": "string",
    "dataSourceId": "string",
    "status": "STARTING | IN_PROGRESS | COMPLETE | FAILED | STOPPING | STOPPED",
    "statistics": {
      "numberOfDocumentsScanned": 0,
      "numberOfNewDocumentsIndexed": 0,
      "numberOfModifiedDocumentsIndexed": 0,
      "numberOfDocumentsDeleted": 0,
      "numberOfDocumentsFailed": 0,
      "numberOfDocumentsSkipped": 0,
      "numberOfMetadataDocumentsScanned": 0,
      "numberOfMetadataDocumentsModified": 0
    },
    "failureReasons": ["string"],
    "startedAt": "timestamp",
    "updatedAt": "timestamp",
    "textReadyAt": "timestamp"
  }
}
```

Syncing is incremental. Queries before `COMPLETE` return nothing for
the new documents.

### Retrieve

`POST /knowledgebases/{knowledgeBaseId}/retrieve`. The reference syntax
for a managed knowledge base:

```json
{
  "retrievalQuery": { "text": "string" },
  "retrievalConfiguration": {
    "managedSearchConfiguration": {
      "filter": {},
      "numberOfResults": 8,
      "rerankingModelType": "MANAGED | CUSTOM | NONE",
      "rerankingConfiguration": {}
    }
  },
  "nextToken": "string"
}
```

`numberOfResults` accepts 1 to 100. `rerankingModelType` defaults to
`MANAGED`. `filter` is one of `equals`, `notEquals`, `greaterThan`,
`greaterThanOrEquals`, `lessThan`, `lessThanOrEquals`, `in`, `notIn`,
`listContains`, `andAll`, `orAll`, each with a `key` and a `value`.

The request for this project, limited to one data source:

```json
{
  "retrievalQuery": { "text": "how is free cash flow defined" },
  "retrievalConfiguration": {
    "managedSearchConfiguration": {
      "numberOfResults": 8,
      "filter": { "in": { "key": "_data_source_id", "value": ["<data source id>"] } }
    }
  }
}
```

With a sidecar attribute the filter is
`{ "equals": { "key": "source_type", "value": "theory" } }`.

Each result carries `content.text`, `location.s3Location.uri`, `score`,
`metadata` and `documentId`. No page says whether a managed knowledge
base returns a page number. T04's `locator` depends on it.
**Unverified** until the first `Retrieve`.

## IAM actions

| Call | Caller | Actions | Resource |
| --- | --- | --- | --- |
| `CreateKnowledgeBase` | CloudFormation execution role | `bedrock:CreateKnowledgeBase`, `bedrock:GetKnowledgeBase`, `bedrock:TagResource`, `bedrock:ListTagsForResource`, `iam:PassRole` on the service role with `iam:PassedToService` = `bedrock.amazonaws.com` | `CreateKnowledgeBase` has no resource type, so `*`. The others take the knowledge base ARN |
| `CreateDataSource` | CloudFormation execution role | `bedrock:CreateDataSource`, `bedrock:GetDataSource`, `bedrock:GetKnowledgeBase` | Knowledge base ARN |
| `StartIngestionJob` | `EngineFn` | `bedrock:StartIngestionJob`, `bedrock:GetIngestionJob`, `bedrock:ListIngestionJobs`, and `bedrock:ListKnowledgeBaseDocuments` if T03 lists failed keys | Knowledge base ARN |
| `Retrieve` | `EngineFn` | `bedrock:Retrieve` | Knowledge base ARN |
| Ingestion and query | Service role, assumed by `bedrock.amazonaws.com` with `aws:SourceAccount` and `aws:SourceArn` conditions | `s3:ListBucket` on the bucket, `s3:GetObject` on the three prefixes, `cloudwatch:PutMetricData` with `cloudwatch:namespace` = `AWS/Bedrock/KnowledgeBases` | Bucket and prefixes |
| MCP server | The person's local profile | `bedrock:Retrieve`, `bedrock:ListKnowledgeBases`, `bedrock:GetKnowledgeBase`, `bedrock:ListDataSources`, `bedrock:ListTagsForResource` | Knowledge base ARN; `ListKnowledgeBases` needs `*` |

The service role needs no `bedrock:InvokeModel`. The bucket uses SSE-S3,
so no KMS statement is needed. The CloudFormation handlers also list
`bedrock:UpdateKnowledgeBase`, `bedrock:UpdateDataSource`,
`bedrock:DeleteKnowledgeBase`, `bedrock:DeleteDataSource` and
`bedrock:ListDataSources` for update and delete. The create handler
also names `bedrock:AssociateThirdPartyKnowledgeBase` and KMS actions,
which apply to third-party stores and customer-managed keys. If the
fallback custom resource is used, its policy is the first row.

Ingestion logs per document are optional. Turning them on needs
`bedrock:AllowVendedLogDeliveryForResource` and a CloudWatch Logs
delivery. `Retrieve` is a CloudTrail data event and is not logged by
default.

## Prices and monthly estimate

| Item | Price (US dollars) |
| --- | --- |
| Storage | 5.00 per GB-month of raw data |
| `Retrieve` | 1.00 per 1,000 calls |
| Agentic retrieval | 4.00 per 1,000 calls, plus 1.00 per 1,000 underlying `Retrieve` calls |
| Parsing, managed embedding, managed reranking | 0 |

The bucket on 17 November 2026, 9:33 PM Hong Kong time, under
`theory/`: 178 PDFs, 1,960,101,332 bytes, no sidecars.

| Case | Size | Storage a month |
| --- | --- | --- |
| Everything | 1.96 GB | 9.80 |
| Books with a text layer only (131 files) | 0.92 GB | 4.62 |
| At the cap `KB_MAX_RAW_BYTES` (2,147,483,648 bytes) | 2.15 GB | 10.74 |

Retrieval adds 5.00 at the cap of 5,000 calls. One evaluation run is 20
calls, or 0.02. The ceiling under both caps is 15.74 a month. If AWS
counts a GB as 2^30 bytes the storage figures are 7% lower.

Calls through the MCP server are billed and bypass the system's
counter, as the plan already says.

## Scanned books

47 of the 178 PDFs have no text layer (page images only). They are
1,035,967,727 bytes, 53% of the bucket. The other 131 files are
924,133,605 bytes. All 20 evaluation questions point at books with a
text layer.

What is known:

- AWS lists scanned documents among the types Smart Parsing handles.
- Parsing is free, so scanned books cost only their storage.
- A third-party test reports that a small PDF with no text layer was
  ingested and retrieved. It is one synthetic file and is treated as
  **unverified** here.
- `imageExtractionConfiguration` covers "embedded visuals in .pdf". No
  page says whether a scanned page needs it.
- Extracted text is limited to 30 MB per file. A book is far below it.

What is unknown: whether a 500-page scan parses fully, and whether its
formulas are readable. Only a sync can answer.

Options for the owner:

1. Sync all 178 files, then judge the scans by hand. Storage is 9.80 a
   month. Removing the 47 files later is 26% of the documents, above
   the 15% guard, so it would need two removals or a raised threshold.
2. Sync the 131 text books first, then add three scanned books as a
   trial. Storage starts at 4.62 a month. Adding files never meets the
   guard. This needs the owner to move the 47 files to a prefix outside
   `theory/`, such as `scans/`.

Option 2 is the recommendation. The evaluation in T05 is unaffected,
and the trial answers the question for the cost of three files.

The owner chose option 2 on 17 November 2026 (Hong Kong). The 47 files
move from `theory/` to `scans/` before the first sync. Three of them
are the later trial. The move runs from an identity that can write the
bucket.

One PDF with a text layer has no space characters in that layer. Its
keyword matches may be poor. T05's hand check should include it.

## File size

- The S3 connector page says `maxFileSizeInMegaBytes` defaults to
  `"500"`.
- The sync page for managed knowledge bases points to the quota
  "Ingestion job file size", which is 50 MB for "a file with text
  content" and is listed without the "Managed Knowledge Bases" label.
- The managed quota list has "Individual file extracted text size":
  30 MB.

No page says whether a megabyte is 1,000,000 or 1,048,576 bytes. The
largest file in the bucket is 49,917,691 bytes, so every file is under
50 MB by either reading. `kb_sync.problems` should keep the plan's
check at 50,000,000 bytes. The first sync shows the truth in
`numberOfDocumentsFailed` and `numberOfDocumentsSkipped`.

## Tests

The checks behind this memo, and what they miss:

- The four project requests pass `botocore.validate.validate_parameters`
  for their operations in botocore 1.44.3. `overrideSearchType` inside
  `managedSearchConfiguration` is rejected by the same check.
- The request the first deploy sent, with `FIXED_SIZE` at 800 tokens
  and 15% overlap, also passes that check.
- The probe stack included that fixed-size chunking. Its two Bedrock
  resources pass the `ap-southeast-1` resource schemas with a JSON
  Schema validator.
- Neither check sees the service rule. The deploy is what rejected the
  chunking strategy.

T02 adds the Jest assertions the plan lists. T03 and T04 add engine
tests with a stubbed Bedrock client.

## Production signals

- `RawDataSize` (Gigabytes) per knowledge base, after each ingestion
  job.
- `Invocations`, `ClientErrors`, `ServerErrors` and `Throttles` with the
  dimensions `Operation` and `KnowledgeBaseId`.
- Ingestion job statistics from `GetIngestionJob`.
- The console page is under Amazon Bedrock AgentCore, Built-in tools,
  Knowledge Base.

## History

- 27 June 2026: issue 2531 opened against `AWS::Bedrock::KnowledgeBase`.
- 9 July 2026: aws-cdk pull request 38275 merged with
  `EmbeddingModelArn` optional.
- 22 September 2026: MCP server 1.1.2 published.
- 1 October 2026: the current knowledge base prices took effect in the
  price list.
- 17 November 2026: this memo. The owner had uploaded the PDFs (O12) and
  the questions file (O13). The same evening the owner chose scanned-book
  option 2, a `RawDataSize` alarm at 2.0 GB, and a boto3 pin of 1.44.3.

## Open questions

- Does the first deploy of `CfnKnowledgeBase` with managed embedding
  succeed in `ap-southeast-1`? The knowledge base was created on
  17 November 2026 (Hong Kong). The data source was rejected for the
  `FIXED_SIZE` strategy it was sent, and the stack rolled back. The
  follow-up omits ingestion settings.
- Does `Retrieve` return a page number, and does the `_data_source_id`
  filter work? The first `Retrieve` in T05 answers both.
- Is the default deletion protection status enabled? T02 sets it
  explicitly, so the answer does not block.
- Are formulas readable after parsing? T05's hand check answers it.
