# Plan: Read the managed knowledge base's passage locations

**Status**: Approved
**Zone**: yellow

## Goal

The first live `kb_eval` scored 0 of 20. A managed knowledge base
returns each passage's location as an HTTPS object URL with the key
percent-encoded, for example
`https://<bucket>.s3.<region>.amazonaws.com/theory/Investment%20Analysis.pdf`,
and the page as `_excerpt_page_number`. `kb_client._map` expected
`s3://<bucket>/<key>` and `x-amz-bedrock-kb-document-page-number`, so
every `document` came back percent-encoded and every `locator` empty.
No passage matched its question's file name.

Scoring the same 20 live responses with the key decoded gives 17 of 20
at 8 and 16 of 20 at 3, which meets both targets.

## Non-goals

- Changing the evaluation rule or targets.
- Splitting the four books that failed ingestion.

## Files

- `backend/lambda/engine/kb_client.py`: decode both URI forms, read the
  page from `_excerpt_page_number` and fall back to the old key.
- `backend/lambda/engine/test_kb_client.py`: a passage in the managed
  form maps to the plain file name, folder, and page.

## Invariants this change preserves

- Passage text is never logged.
- The folder filter and the monthly cap are unchanged.
- An `s3://` location still maps as before.

## Done when

- `python3 -m unittest discover -s backend/lambda/engine -p 'test_kb_*.py'`
  passes.
- After deploy, **Run now** on `kb_eval` reports at least 16 of 20 at 8
  and 12 of 20 at 3.

## Rollback

Revert the commit. The evaluation goes back to scoring 0.

## Open questions

None.
