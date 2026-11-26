# Plan: Clear open code scanning alerts

**Status**: Done
**Zone**: yellow

## Goal

Clear the two open Semgrep alerts. The logger line mentions a store
read without using a credential word, and the data-source probe refuses
any URL that is not https before it calls urllib.

## Non-goals

- No change to which secret fields are read or cached.
- No new network calls.

## Files

- `backend/lambda/engine/secrets_read.py`
- `backend/lambda/engine/test_secrets_read.py`
- `scripts/probe_data_sources.py`

## Invariants this change preserves

A failed secret read still raises `NotConfigured`, still omits the
secret id and the secret value from the log, and is still not cached.

## Done when

`python3 -m unittest backend/lambda/engine/test_secrets_read.py` passes.
The probe rejects a non-https URL before `urlopen`.

## Rollback

Restore the previous log text and the unguarded `urlopen`.

## Open questions

None.
