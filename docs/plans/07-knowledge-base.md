# Plan: M07 knowledge base

**Status**: Draft
**Zone**: red (CDK resources, IAM, the register's citations)

## Goal

A Bedrock **Managed** Knowledge Base over the owner's finance PDFs, so
that code and people can ask "what do the books say about X" and get
passages with their source. It holds the theory: formulas, rules,
logic. This milestone also measures whether retrieval is good enough
for formulas, attaches citations to the register, and connects the
knowledge base to Cursor and Claude through the AWS MCP server.

## Non-goals

- No company filings or news in the knowledge base. It is for theory
  and the system's own journal.
- No answer generation by Bedrock. Managed knowledge bases do not
  support `RetrieveAndGenerate`. The system retrieves passages and the
  committee (M08) reasons over them.
- No agentic retrieval in the pipeline (it costs four times more per
  call).
- No PDFs in git. The owner uploads to S3.
- No model call in this milestone.

## What was verified when this plan was written

Recheck every line in T01. Services change.

T01 rechecked this list on 17 November 2026 (Hong Kong). The results
and the corrections this plan needs are in
`docs/research/managed-kb.md`, under "Recheck of the plan's verified
list" and "What the plan must change". T02 below is the approved
design. Later steps still carry their original text where the memo's
table names a correction.

Owner decisions, the same evening, with the review of 17 November 2026
(Hong Kong) folded in:

- Scanned books: option 2 in the memo. The 47 files with no text layer
  move from `theory/` to `scans/` before the first sync. That sync
  covers the 131 text books. Three scanned books are a later trial.
- Alarm: `RawDataSize` above 2.0. The unit on the metric is gigabytes.
  The first sync shows whether that is decimal or binary, and the
  threshold is revisited after that sync. A missing sample keeps the
  previous alarm state, so a breach stays up until a later sync
  publishes a value at or under 2.0. Nothing is notified, matching the
  other alarms.
- `AdminApiFn` and `EngineFn` bundle `boto3==1.44.3` and
  `botocore==1.44.3`, because both are built from the engine directory.
  The change is `m07-pin-boto3.md`.

- Managed Knowledge Base (`type: MANAGED`) is available in
  `ap-southeast-1`. Hybrid search is always on. Embedding, reranking
  and parsing are included and managed. Storage is internal to AWS.
- Price: 5 US dollars per GB of raw data per month, plus 1 per 1,000
  `Retrieve` calls.
- `Retrieve` takes `managedSearchConfiguration` (not
  `vectorSearchConfiguration`). There is no `overrideSearchType`. The
  filters `startsWith` and `stringContains` are not supported.
- S3 data source. File limit 50 MB. Types: PDF, Markdown, text, HTML,
  Word, Excel, CSV. Optional `<file>.metadata.json` sidecar, at most
  10 KB.
- With managed embedding the data source omits chunking. The service
  default is 300 tokens with 20% overlap, and Smart Parsing. The first
  deploy on 17 November 2026 (Hong Kong) rejected a chunking strategy.
  The memo records the error.
- Deleting more than 15% of documents in one sync is blocked by
  default.
- Quotas: 200 data sources per knowledge base, 600 `Retrieve` calls a
  minute.
- CloudWatch metric `RawDataSize` in the namespace
  `AWS/Bedrock/KnowledgeBases`.
- CloudFormation could not create a managed knowledge base with
  managed embedding (issue 2531 on the CloudFormation coverage
  roadmap, open when this was written). The fallback is an
  `AwsCustomResource` that calls `CreateKnowledgeBase`.
- The MCP server `awslabs.bedrock-kb-retrieval-mcp-server` supports
  managed knowledge bases and finds them by the tag
  `mcp-multirag-kb=true`.

## Merge and deploy order

The pin, the research memo and the knowledge base are on `main`. The
first deploy created the knowledge base, then failed on the data
source, and CloudFormation rolled the new resources back. The
follow-up omitted ingestion settings. Its deploy on 18 November 2026
(Hong Kong) created the role, the knowledge base, the three data
sources in order, and the alarm. Nothing is ingested yet.

## Files

```
docs/research/managed-kb.md
backend/infrastructure/lib/knowledge-base.ts          (red)
backend/infrastructure/lib/findingalpha-stack.ts  functions.ts  alarms.ts  outputs.ts  api-routes.ts
backend/infrastructure/test/findingalpha-stack.test.ts
backend/lambda/engine/kb_sync.py     test_kb_sync.py
backend/lambda/engine/kb_client.py   test_kb_client.py
backend/lambda/engine/kb_eval.py     test_kb_eval.py
backend/lambda/engine/jobs_handler.py  api_handler.py
contracts/budgets.json   contracts/methodology.json    (citations; red)
apps/admin_web/src/pages/KnowledgeBasePage.tsx         (+ nav, mock, test)
.cursor/mcp.json
docs/deployment/knowledge-base.md
```

## Invariants this change preserves

- The knowledge base bucket is private. Only the owner, `EngineFn` and
  the Bedrock service role can read it.
- Cost caps are enforced in code: no sync above `KB_MAX_RAW_BYTES`, no
  retrieval above `KB_MAX_RETRIEVALS_PER_MONTH`. Both fail closed.
- Retrieved text is data, not instructions. Nothing in a passage can
  change what the code does.
- A register entry is `cited` only with a document, a locator and a
  quote that a person has checked.
- Book titles, passages and the evaluation questions stay out of git,
  except the short quote in a citation (at most 200 characters).

## Steps

### M07-T01 Spike and memo

No resources are created in this step. Read the current AWS
documentation and API reference and write
`docs/research/managed-kb.md`:

1. Is issue 2531 fixed? If yes, use `CfnKnowledgeBase` in T02. If no,
   use the custom resource.
2. The exact request for `CreateKnowledgeBase` with `type: MANAGED`,
   for `CreateDataSource` on S3 with fixed-size chunking, for
   `StartIngestionJob`, and for `Retrieve` with
   `managedSearchConfiguration` and a metadata filter. Paste the JSON
   shapes from the reference.
3. The current prices. If storage is not 5 per GB or retrieval is not
   1 per 1,000, stop and tell the owner with the new monthly estimate.
4. Whether the managed type needs any model access to be enabled in
   the account.
5. The IAM actions each call needs.

### M07-T02 CDK resources

`lib/knowledge-base.ts`, one function `defineKnowledgeBase(scope,
deps)`. Approved on 17 November 2026 (Hong Kong), including the review
of that plan. `CfnKnowledgeBase` is the resource. The first deploy
created it, then the data source rejected a chunking strategy and the
stack rolled back. The follow-up omits `vectorIngestionConfiguration`,
and its deploy on 18 November 2026 (Hong Kong) succeeded.
`AwsCustomResource` stays unused. **Done.**

1. **Service role**, inline policy on the role itself so the policy
   exists when the knowledge base is created. Trusted by
   `bedrock.amazonaws.com` with `aws:SourceAccount` and `aws:SourceArn`
   matching `knowledge-base/*` (the knowledge base ARN does not exist
   yet, so a condition on one ARN cannot be written). `s3:ListBucket`
   on the whole bucket, as the service documents it. `s3:GetObject`
   only under `theory/`, `formula-notes/` and `journal/`.
   `cloudwatch:PutMetricData` with `cloudwatch:namespace` equal to
   `AWS/Bedrock/KnowledgeBases`. No `bedrock:InvokeModel`.
2. **Knowledge base** named `findingalpha-theory`, type `MANAGED`,
   managed embedding, no embedding model ARN. Tags
   `mcp-multirag-kb=true` and `Project=Finding Alpha`. Removal policy
   retain-except-on-create: a rolled-back create is deleted, a knowledge
   base that exists is kept when the stack is deleted, and a replacement
   keeps the previous one.
3. **Three data sources**, names `theory`, `formula-notes` and
   `journal`, type `MANAGED_KNOWLEDGE_BASE_CONNECTOR`, one inclusion
   prefix each. `scans/` and `eval/` are outside all three. The data
   source omits `vectorIngestionConfiguration`. Managed embedding
   rejects a chunking strategy, and Smart Parsing is the service
   default, so both settings stay out of the request. The index uses
   300 tokens with 20% overlap. File size cap 50 MB. Data deletion
   policy `DELETE`. Deletion protection enabled at 15%. No sync
   schedule, so deploy creates the resources and ingests nothing. The
   three data sources are created one after another: `theory`, then
   `formula-notes`, then `journal`. Each create is asynchronous, and
   the next starts when the previous one is available. The data sources
   use the default removal policy, so removing one deletes it. The PDFs
   in S3 are the source of truth, and a re-sync rebuilds the index.
   Whether a different chunk size can be set is untested. The user
   guide still lists fixed size and none for a managed knowledge base,
   and the first deploy only shows that managed embedding rejected the
   `FIXED_SIZE` request it was sent.
4. Environment for `EngineFn`: `KNOWLEDGE_BASE_ID` and
   `KB_DATA_SOURCE_IDS` (JSON map of prefix to id).
5. IAM for `EngineFn`: `bedrock:Retrieve`, `bedrock:StartIngestionJob`,
   `bedrock:GetIngestionJob`, `bedrock:ListIngestionJobs` and
   `bedrock:ListKnowledgeBaseDocuments` on the knowledge base ARN.
   `AdminApiFn` gets none.
6. Alarm: `RawDataSize` above 2.0, dimension `KnowledgeBaseId` =
   `knowledge-base/<id>`. A missing sample keeps the previous state
   (`treatMissingData: ignore`). No notification target, same as the
   other alarms. The threshold is revisited after the first sync
   reports whether a gigabyte is decimal or binary.
7. Output: `KnowledgeBaseId`. `KbBucketName` already exists.
8. Jest assertions: list is bucket-wide and object reads are the three
   prefixes; `AdminApiFn` has no Bedrock statement; both tags are set;
   the knowledge base is retain-except-on-create and the data sources
   are not retained; the data sources are created in the order
   `theory`, `formula-notes`, `journal`; the alarm threshold is 2 and
   a missing sample keeps the previous state; there is no sync
   schedule; no data source sets `VectorIngestionConfiguration`.
   `AWS::Bedrock::DataSource` is added to the untagged-types
   list, because that resource has no tag property.

The schedule `findingalpha-kb-sync-check` is created in T03. It does
not start the first sync. Run now does.

After the first sync, `numberOfDocumentsScanned` is 131 for `theory/`
and 0 for the other two. A larger theory count means the prefix filter
was ignored. The `RawDataSize` value from that sync shows whether a
gigabyte here is decimal or binary, and the alarm threshold is
revisited from that value.

### M07-T03 Sync

`kb_sync.py`:

1. `manifest()`: list every object under the three prefixes with key,
   size and ETag. Ignore `eval/`. Split into documents and
   `.metadata.json` sidecars.
2. `problems(manifest)`: files over 50 MB; unsupported extensions;
   sidecars over 10 KB; sidecars without a document.
3. `decide(manifest, state)`. Approved on 18 November 2026 (Hong Kong),
   with the three choices from the review of this step:
   - Total bytes above `KB_MAX_RAW_BYTES`: status `blocked_size`. Do
     not sync.
   - More than 15% of the previously known documents are gone, checked
     per data source: status `blocked_deletion`. Do not sync any
     source. Run now again with `{"confirmDeletion": true}` allows it.
     The service can still skip its own delete phase; the result then
     names the shortfall.
   - The manifest hash equals the stored one and no job is running:
     status `unchanged`.
   - Otherwise start one ingestion job for each data source whose
     files changed, and store the job ids.
   - A listed problem (step 2) is stored and logged, and that file is
     left out of the sync. It does not block the other files.
   - A prefix with no files, and no files in the last sync, is not
     started. A prefix that used to have files still follows the
     deletion rule.
4. `poll(state)`: for stored job ids, read the job status and the
   statistics (scanned, indexed, failed). When all are complete, store
   the manifest hash, document count, bytes and time in `KB#state`.
   Failed documents are listed by key. When some jobs complete and
   others fail, the completed folders are saved and the next run starts
   only the rest. The manifest hash stays unset until every folder
   matches.

The job is `kb_sync_check`. It runs `decide` then `poll`. `tick` keeps
polling while a job is in progress, through the job state it already
resumes. The schedule `findingalpha-kb-sync-check` (daily 05:30 Hong
Kong) is created in this step. Until the first Run now, the schedule
returns `awaiting_first_sync` and starts nothing. Run now is
`POST /jobs/kb_sync_check/run`. The Knowledge base page uses
`POST /kb/sync`, which starts the same job and accepts the same body.

A failed or stopped ingestion clears the saved job ids and keeps the
last good manifest, so the next run can start again. The idempotency
token includes the previous job id, so a retry does not reuse it.
Starting a sync does not replace that manifest. An ingestion still
running after 24 hours is stopped (`bedrock:StopIngestionJob`), and the
owner can stop one from the dashboard with `{"stop": true}`. A blocked
deletion or a problem list is written on `KB#state` and on the run
row. Confirm and Stop are on the Knowledge base page. An API
key cannot confirm a deletion, stop a sync, or start the first sync.
The roadmap row stays `todo` until the first real sync.

Tests with a stubbed Bedrock client: each status; the hash ignores
listing order; a sidecar change counts as a change; a failed document
is reported.

### M07-T04 Retrieval client

`contracts/budgets.json` (first version):

```json
{
  "version": 1,
  "kb": { "maxRetrievalsPerMonth": 5000, "warnShare": 0.8, "defaultTopK": 8, "maxTopK": 12 }
}
```

`kb_client.py`:

- `retrieve(query, top_k=None, source_types=None)` returns a list of
  passages: `text`, `document` (file name), `locator` (page number or
  section when the service returns one), `score`, `sourceType`
  (`theory`, `formula-notes`, `journal`, from the S3 key prefix).
- Before the call: read `USAGE#<yyyy-mm>` / `KB`. At or above the cap
  raise `KbBudgetExceeded`. After the call: add one with an atomic
  `ADD` update, on both the month row and the `USAGE#<date>` row.
- `source_types` becomes an `in` filter on `_data_source_id`, using
  the ids in `KB_DATA_SOURCE_IDS`. When that map is missing, the
  results are filtered by key prefix after the call. No sidecar is
  required for the folder filter.
- Query text is cut to 1,000 characters. `top_k` is clamped to
  `maxTopK`.
- A per-invocation cache keyed by the query and arguments.
- Never logs passage text. Logs the query hash, the count and the
  latency.

Tests: the cap refuses at the limit; the reservation is taken before
the call and released when the call raises; the counter increments
once per call and not on a cache hit; results are mapped; prefix
filtering works without sidecars. The roadmap row stays `todo` until
a live retrieval confirms the folder filter and the page number.

### M07-T05 Evaluation

Needs O12 (PDFs uploaded) and O13 (questions file).

`kb_eval.py`, job `kb_eval` (manual run): for each question in
`eval/questions.json`, retrieve the top 8. A question is a **hit at
8** when some passage comes from `expectedDocument` and contains
`expectedText` after lower-casing and collapsing whitespace. Also
record **hit at 3**. Store the run under `KB#eval` with per-question
results (question id, hit rank or `null`, the documents returned; no
passage text). Each question also carries `page` and `formula`. They
are for the hand check below. The job accepts them and does not score
them.

Targets: at least 16 of 20 at 8, and at least 12 of 20 at 3. The job
refuses until `KB#state` has a manifest hash. Below either target the
run is failed and the message starts with `below target`. The results
are stored either way. A key cannot start this job.

Then read the returned passages for the formula questions by hand
(through the MCP server, T07) and note in the memo whether the
formulas are readable. PDF parsers often scramble mathematics.

If a target is missed, or formulas are unreadable, **stop and ask**.
The fallback to put to the owner is formula notes: for each formula
that matters, a short Markdown file under `formula-notes/` with the
formula in plain text, what each symbol means, and the book and page.
The owner writes or approves each note.

On 19 November 2026 (Hong Kong) the targets were met (17 of 20 at 8,
16 of 20 at 3), but the parser dropped or garbled most symbolic
formulas. The owner chose formula notes. The drafts are in
`docs/knowledge-base/formula-notes/`, one per formula the register
uses where a book in `theory/` supports it. Each holds the book's
formula, not the register's, so T06 can compare the two. Once approved
they are uploaded to `formula-notes/` and synced. T05 is done when that
sync completes and a retrieval with the `formula-notes` filter returns
each note.

The 11 notes were uploaded and synced on 19 November 2026 (11 scanned,
11 indexed). On 20 November each note was the top result for its own
query with the `formula-notes` filter, with its formula intact. T05 is
done.

### M07-T06 Cite the register

Add a third status to `methodology.validate`: `owner_accepted`, which
requires an `acceptedNote` string. Bump the register version.

For every entry in the register (universe rules, each factor,
composite, screen, backtest):

1. Query the knowledge base, through the MCP server, with the entry's
   name and formula.
2. If the books support it: fill `citation` (`document`, `locator`,
   `quote` of at most 200 characters) and set `status: cited`.
3. If the books define it differently: write both definitions in a
   table for the owner. Do not change the formula yourself.
4. If the books say nothing: list it.

Post the three lists in chat. The owner decides per entry: change the
formula (then M05's golden file and M06's backtest are rerun), keep it
as `owner_accepted` with a note, or remove it. Apply the decisions in
one red-zone pull request.

### M07-T07 MCP server

`.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "findingalpha-kb": {
      "command": "uvx",
      "args": ["awslabs.bedrock-kb-retrieval-mcp-server==<pinned version>"],
      "env": {
        "AWS_PROFILE": "findingalpha-kb-read",
        "AWS_REGION": "ap-southeast-1",
        "KB_INCLUSION_TAG_KEY": "mcp-multirag-kb",
        "BEDROCK_KB_RERANKING_ENABLED": "false"
      }
    }
  }
}
```

Pin the version (1.1.2 was current when this was written). Reranking
is off in the server because the managed knowledge base already
reranks. The AWS profile is a local profile of the person using it,
with read-only access to `bedrock:Retrieve`,
`bedrock:GetKnowledgeBase`, `bedrock:ListKnowledgeBases`,
`bedrock:ListDataSources`, `bedrock:ListTagsForResource`.
`GetKnowledgeBase` is required because server 1.1.2 reads the
knowledge base before it queries. No credentials in git.

`docs/deployment/knowledge-base.md`: how the owner uploads PDFs, the
sidecar format, the caps, how to read the Knowledge base page, the
same MCP block for Claude Desktop, and this warning: queries made
through the MCP server are billed by AWS but are not counted by the
system's own monthly cap.

### M07-T08 API and dashboard

Implemented. The page is `/knowledge-base`.

Routes: `GET /kb/status`, `POST /kb/sync`, `GET /kb/eval/latest`.
`kb_eval` is on the manual-run list. `POST /kb/sync` accepts an empty
body, `{"confirmDeletion": true}`, or `{"stop": true}`. A key cannot
confirm a deletion, stop a sync, or start the first sync. The status
read does not call Bedrock. While a sync is running, the poll saves
how many documents were scanned, indexed, and failed. The page shows
those counts, and it keeps the document count and size from the last
finished sync until this one completes. **Sync now** is hidden while
a sync is running, while a deletion needs confirmation, and while the
files are over the size cap.

`contracts/budgets.json` holds the rates the page uses and M08 can
reuse: `storageUsdPerGb` 5 and `retrievalUsdPerThousand` 1. Storage
is a full month at the current size, in decimal gigabytes
(`bytes / 1_000_000_000`). Retrievals are the spend so far this month.
The page shows the two figures separately. Hit counts and the
retrieval counter are whole numbers, including when DynamoDB returns
them as decimals. The evaluation response is the question id and hit
rank. Passage text stays out.

`KnowledgeBasePage.tsx`:

- KPI tiles: documents, size against the cap (progress bar),
  retrievals this month against the cap, last sync time and status,
  evaluation hits.
- Problems list: oversized files, unsupported types, failed documents,
  a blocked sync with its reason and, for a blocked deletion, a
  Confirm button behind a dialog.
- Buttons: Sync now (hidden while a sync is running or blocked), Run evaluation.
- Evaluation table: question id, hit rank.
- Storage for a month at the current size, and retrievals so far this month, shown separately.

Nav entry "Knowledge base" (`bi-book`), mock fixtures, unit tests,
smoke test line. Add the knowledge base line to the Costs data used
in M08.

## Done when

- Stack tests and engine tests pass.
- The knowledge base exists, the first sync completed, and the page
  shows documents and size.
- The evaluation run meets both targets, or the owner chose a fallback
  and the rerun meets them.
- Every register entry is `cited` or `owner_accepted`. The Methodology
  page shows zero provisional entries.
- The MCP server answers a query in Cursor. Paste the tool call (not
  the passage) in the pull request.
- The memo `docs/research/managed-kb.md` is merged.

## Rollback

Turn the schedule's job off by reverting. The knowledge base and
bucket are retained. To stop cost entirely the owner deletes the
knowledge base in the console; the PDFs stay in S3.

## Open questions

- An AWS budget alert on the Bedrock service at 15 US dollars would
  catch use that bypasses the system's counter. It needs the owner's
  decision because budgets are account-wide.
- Whether the default 300-token chunks suit the owner's books. T05
  answers it. A different chunk size is untested. The user guide still
  lists fixed size and none, and the first deploy only rejected the
  `FIXED_SIZE` request it was sent.
