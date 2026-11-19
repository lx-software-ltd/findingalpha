# Operating the knowledge base

The bucket, the knowledge base, and the three data sources are created
by the `findingalpha` stack. This page is how the owner adds books,
reads a sync, and connects Cursor or Claude Desktop. The knowledge base
id stays out of git. Read it from the stack output `KnowledgeBaseId`.

## Uploads

Put files in `theory/`, `formula-notes/`, or `journal/`. `scans/` and
`eval/` are not data sources. A file may be PDF, Markdown (`.md` or
`.markdown`), text, HTML (`.html` or `.htm`), Word, Excel, or CSV.
The sync also accepts `.pptx`, but a managed knowledge base has not
confirmed that type, so a PowerPoint file can come back as a failed
document. The limit is 50 MB a file. The sync refuses to
start when the three prefixes together exceed `KB_MAX_RAW_BYTES`
(2 GB unless the stack sets another value).

A sidecar sits beside its file, named `<file>.<extension>.metadata.json`,
and stays under 10 KB:

```json
{
  "metadataAttributes": {
    "source_type": { "value": { "type": "STRING", "stringValue": "theory" } }
  }
}
```

The folder filter does not need a sidecar. It uses the data source id.

## Sync

The first sync is **Sync now** on the Knowledge base page, signed in
as the owner. The System page can still start `kb_sync_check` with
Run now. The daily schedule does not start the first sync. While
Bedrock is working, **Sync now** is hidden and the page shows the
sync as running. Document count and size stay at the last finished
sync until this one completes. Scanned, indexed, and failed counts
appear after the sync job's next check. The page reads those saved
counts and does not ask Bedrock. The engine stops an ingestion that
runs past its limit, and the owner can stop one sooner with **Stop**.

A prefix with no files, and none in the last sync, is not started. A
problem file is recorded and left out. More than 15% of a folder gone
waits for **Confirm deletion**. **Sync now** stays hidden until that
confirmation, and it stays hidden when the files are over the size cap.

The page shows the document count, size against the cap, retrievals
this month, the last sync in plain language, evaluation hits, and
problem files. Storage for a month at the current size is estimated
at 5 US dollars per decimal gigabyte. Retrievals so far this month
are estimated at 1 US dollar per thousand. The page shows those
figures separately. Both rates are in `contracts/budgets.json`.

## Formula notes

The parser drops or garbles most display equations in the PDFs. A
formula the register relies on is kept as a Markdown note in
`docs/knowledge-base/formula-notes/`: the book's formula in plain text,
its symbols, the book and page, and a short quote. The owner approves
a note in its pull request. After merge, upload the folder and press
**Sync now**:

```sh
aws s3 sync docs/knowledge-base/formula-notes/ \
  s3://<kb bucket>/formula-notes/ --region ap-southeast-1 --delete
```

`--delete` removes a note from the bucket when it is removed from git.

## Retrieval cap

`contracts/budgets.json` allows 5,000 retrievals a month. At 4,000 the
engine logs a warning and still answers. At 5,000 it refuses. The
counter is `USAGE#<yyyy-mm>` / `KB` in the records table.

## MCP server

Create a local AWS profile named `findingalpha-kb-read`. It needs:

- `bedrock:Retrieve`, `bedrock:GetKnowledgeBase`,
  `bedrock:ListDataSources`, and `bedrock:ListTagsForResource` on the
  knowledge base ARN
- `bedrock:ListKnowledgeBases` on `*`

`GetKnowledgeBase` is there because server 1.1.2 reads the knowledge
base before it queries. Do not add `bedrock:AgenticRetrieveStream`.

Cursor reads `.cursor/mcp.json`. The server runs through `uvx`, so
`uv` has to be installed. Without the `findingalpha-kb-read` profile
the server does not start. The same block, with the same profile, is
what Claude Desktop uses. Reranking in the server is off because the
managed knowledge base already reranks.

Queries made through the MCP server are billed by AWS. They are not
counted by the system's monthly cap.
