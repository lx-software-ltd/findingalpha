# Plan: Pin boto3 and botocore for the admin and engine Lambdas

**Status**: Draft
**Zone**: yellow

## Goal

Make `AdminApiFn` and `EngineFn` bundle `boto3==1.44.3` and
`botocore==1.44.3`.

Managed knowledge base calls need botocore 1.43.64 or later. The boto3
inside the Lambda Python 3.12 runtime varies by region, so a call that
works in one region can fail in `ap-southeast-1`. Release 1.44.3 is
above that floor. It is the release checked on 17 November 2026 (Hong
Kong): its `Retrieve` input shape has `managedSearchConfiguration`.

The owner chose the boto3 pin the same evening. `AdminApiFn` and
`EngineFn` are both built from `backend/lambda/engine`, so both bundles
install these packages and the runtime copy is unused in each of them.

`boto3==1.44.3` depends on `botocore>=1.44.3,<1.45.0` (PyPI, that same
evening). The request shapes live in botocore. The CDK diff on this
pull request installed boto3 1.44.3 with botocore 1.44.4. Pinning
botocore at 1.44.3 makes the next install the pair that was checked.

## Non-goals

- The pre-token function and the key authorizer. They have their own
  directories and keep the runtime's boto3.
- The knowledge base resources. Those are M07-T02, a separate pull
  request. Merge this pin first.
- An upper bound. Dependabot already watches this requirements file and
  can propose the next 1.x release.

## Files

- `backend/lambda/engine/requirements.txt`
- `backend/lambda/engine/test_boto3_pin.py`

## Invariants this change preserves

- `AdminApiFn` and `EngineFn` stay on Python 3.12 and arm64.
- Local bundling still refuses to copy a macOS wheel. With a real
  requirement, bundling uses the Linux arm64 image. Jest synths with
  `aws:cdk:bundling-stacks: []`, so the unit tests do not pip-install.
- `CDK_SKIP_PYTHON_PIP=1` still copies sources only, for a template-only
  synth.

## Merge order

Merge this into `main` before the knowledge base resources. The memo
can merge beside it. The knowledge base pull request targets the memo
branch until that memo is on `main`. Merging the knowledge base pull
request before that retarget updates the memo branch and leaves
production unchanged.

## Done when

- `python3 -m unittest discover -s backend/lambda/engine -p 'test_*.py'`
- `python3 -m ruff check backend/lambda/engine/test_boto3_pin.py`
- `python3 scripts/check_pii.py`
- `python3 scripts/check_file_length.py`

## Rollback

Restore the comment-only `requirements.txt` and delete the test. The
next deploy uses the runtime's boto3 again for both functions. Nothing
in production reads the pin until that deploy.

## Open questions

None. The deploy shows the zipped bundle size. The arm64 install
already succeeded in the pull request's CDK diff.
