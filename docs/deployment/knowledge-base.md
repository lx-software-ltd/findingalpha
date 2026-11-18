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

The first sync is **Run now** on `kb_sync_check` on the System page,
signed in as the owner. The daily schedule does not start it. While
Bedrock is working the row stays `partial`. The engine stops an
ingestion that runs past its limit, and the owner can stop one sooner.

A prefix with no files, and none in the last sync, is not started. A
problem file is recorded and left out. More than 15% of a folder gone
waits for **Confirm deletion** on the System page.

The Knowledge base page arrives in M07-T08. Until then the System page
is where a sync is started, confirmed, and stopped.

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
