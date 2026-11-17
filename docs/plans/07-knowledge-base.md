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
list" and "What the plan must change". The owner approves the remaining
corrections with T02. The steps below still carry the original text,
apart from the three decisions recorded here.

Owner decisions, the same evening:

- Scanned books: option 2 in the memo. The 47 files with no text layer
  move from `theory/` to `scans/` before the first sync. That sync
  covers the 131 text books. Three scanned books are a later trial.
- Alarm: `RawDataSize` above 2.0 GB.
- `EngineFn` bundles `boto3==1.44.3`. The change is
  `docs/plans/m07-pin-boto3.md`.

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
- Chunking is chosen when the data source is created and cannot be
  changed later: default (300 tokens, 20% overlap), none, or fixed
  size. No semantic chunking.
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
deps)`:

1. **Service role** for Bedrock: trusted by `bedrock.amazonaws.com`
   with `aws:SourceAccount` and `aws:SourceArn` conditions; may list
   and read `KbBucket` under `theory/`, `formula-notes/` and
   `journal/` only.
2. **Knowledge base** named `findingalpha-theory`, type `MANAGED`,
   tagged `mcp-multirag-kb=true` and `Project=Finding Alpha`. Through
   `CfnKnowledgeBase` or, if T01 says so, an `AwsCustomResource` with
   `onCreate` calling `CreateKnowledgeBase` and a physical id taken
   from the response. No `onDelete`: removing the resource from the
   stack must not delete the knowledge base. The custom resource's
   policy lists exactly the actions from T01.
3. **Three data sources**, each on one prefix: `theory`,
   `formula-notes`, `journal`. Chunking: fixed size, 800 tokens, 15%
   overlap. Data deletion policy: retain. This choice is permanent for
   a data source, which is why T05 measures it before anything depends
   on it.
4. Environment for `EngineFn`: `KNOWLEDGE_BASE_ID` and
   `KB_DATA_SOURCE_IDS` (JSON map of prefix to id).
5. IAM for `EngineFn`: `bedrock:Retrieve` on the knowledge base ARN;
   `bedrock:StartIngestionJob`, `bedrock:GetIngestionJob`,
   `bedrock:ListIngestionJobs` on the same. `AdminApiFn` gets none.
6. Alarm: `RawDataSize` above 2.0 GB. The owner set this on
   17 November 2026 (Hong Kong). The metric's unit is gigabytes.
7. Outputs: `KnowledgeBaseId`, `KbBucketName`.
8. Jest assertions: the role's S3 statement is limited to the three
   prefixes; `AdminApiFn` has no Bedrock statement; the tag is set.

Schedule `findingalpha-kb-sync-check` (daily 05:30 Hong Kong).

### M07-T03 Sync

`kb_sync.py`:

1. `manifest()`: list every object under the three prefixes with key,
   size and ETag. Ignore `eval/`. Split into documents and
   `.metadata.json` sidecars.
2. `problems(manifest)`: files over 50 MB; unsupported extensions;
   sidecars over 10 KB; sidecars without a document.
3. `decide(manifest, state)`:
   - Total bytes above `KB_MAX_RAW_BYTES`: status `blocked_size`. Do
     not sync.
   - More than 15% of the previously known documents are gone: status
     `blocked_deletion`. Do not sync. The owner must confirm on the
     dashboard, which calls `POST /kb/sync` with `{"confirmDeletion":
     true}`.
   - The manifest hash equals the stored one and no job is running:
     status `unchanged`.
   - Otherwise start one ingestion job for each data source whose
     files changed, and store the job ids.
4. `poll(state)`: for stored job ids, read the job status and the
   statistics (scanned, indexed, failed). When all are complete, store
   the manifest hash, document count, bytes and time in `KB#state`.
   Failed documents are listed by key.

Jobs: `kb_sync_check` (scheduled; runs `decide` then `poll`; `tick`
keeps polling while a job is in progress) and the route
`POST /kb/sync` (starts `kb_sync_check` now).

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
- `source_types` becomes an `in` filter on the metadata attribute
  `source_type` when sidecars carry it; otherwise filter the results
  by key prefix after the call.
- Query text is cut to 1,000 characters. `top_k` is clamped to
  `maxTopK`.
- A per-invocation cache keyed by the query and arguments.
- Never logs passage text. Logs the query hash, the count and the
  latency.

Tests: the cap refuses at the limit; the counter increments once per
call and not on a cache hit; results are mapped; prefix filtering
works without sidecars.

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

Targets: at least 16 of 20 at 8, and at least 12 of 20 at 3.

Then read the returned passages for the formula questions by hand
(through the MCP server, T07) and note in the memo whether the
formulas are readable. PDF parsers often scramble mathematics.

If a target is missed, or formulas are unreadable, **stop and ask**.
The options to put to the owner:

1. Formula notes: for each formula that matters, a short Markdown file
   under `formula-notes/` with the formula in plain text, what each
   symbol means, and the book and page. The owner writes or approves
   each note. This is the expected fallback.
2. A new data source with different chunking (the old one cannot be
   changed), then re-evaluate.

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
`bedrock:ListKnowledgeBases`, `bedrock:ListDataSources`,
`bedrock:ListTagsForResource`. No credentials in git.

`docs/deployment/knowledge-base.md`: how the owner uploads PDFs, the
sidecar format, the caps, how to read the Knowledge base page, the
same MCP block for Claude Desktop, and this warning: queries made
through the MCP server are billed by AWS but are not counted by the
system's own monthly cap.

### M07-T08 API and dashboard

Routes (red: ask first): `GET /kb/status`, `POST /kb/sync`,
`GET /kb/eval/latest`. `kb_eval` joins the manual-run list.

`KnowledgeBasePage.tsx`:

- KPI tiles: documents, size against the cap (progress bar),
  retrievals this month against the cap, last sync time and status,
  evaluation hits.
- Problems list: oversized files, unsupported types, failed documents,
  a blocked sync with its reason and, for a blocked deletion, a
  Confirm button behind a dialog.
- Buttons: Sync now, Run evaluation.
- Evaluation table: question id, hit rank.
- Estimated monthly cost from size and retrievals.

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
- Whether 800-token chunks suit the owner's books. T05 answers it.
