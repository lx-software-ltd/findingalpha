# Plan: Pin boto3 for the engine Lambda

**Status**: Draft
**Zone**: yellow

## Goal

Make `EngineFn` bundle `boto3==1.44.3`.

Managed knowledge base calls need botocore 1.43.64 or later. The boto3
inside the Lambda Python 3.12 runtime varies by region, so a call that
works in one region can fail in `ap-southeast-1`. Release 1.44.3 is
above that floor. It is the release checked on 17 November 2026 (Hong
Kong): its `Retrieve` input shape has `managedSearchConfiguration`.

The owner chose this pin the same evening. `AdminApiFn` and `EngineFn`
are both built from `backend/lambda/engine`, so both bundles install
this boto3 and the runtime copy is unused in each of them.

The CDK diff job on the pull request already ran that install in the
arm64 build image: boto3 1.44.3 with botocore 1.44.4, which is above
the floor.

## Non-goals

- The pre-token function and the key authorizer. They have their own
  directories and keep the runtime's boto3.
- The knowledge base resources. Those are M07-T02, which is red and
  waits for its own approval.
- An upper bound. Dependabot already watches this requirements file and
  can propose the next 1.x release.

## Files

- `backend/lambda/engine/requirements.txt`
- `backend/lambda/engine/test_boto3_pin.py`

## Invariants this change preserves

- `EngineFn` stays on Python 3.12 and arm64.
- Local bundling still refuses to copy a macOS wheel. With a real
  requirement, bundling uses the Linux arm64 image. Jest synths with
  `aws:cdk:bundling-stacks: []`, so the unit tests do not pip-install.
- `CDK_SKIP_PYTHON_PIP=1` still copies sources only, for a template-only
  synth.

## Done when

- `python3 -m unittest discover -s backend/lambda/engine -p 'test_*.py'`
- `python3 -m ruff check backend/lambda/engine/test_boto3_pin.py`
- `python3 scripts/check_pii.py`
- `python3 scripts/check_file_length.py`

## Rollback

Restore the comment-only `requirements.txt` and delete the test. The
next deploy goes back to the runtime's boto3. Nothing in production
reads the pin until that deploy.

## Open questions

None. The deploy shows the zipped bundle size. The arm64 install
already succeeded in the pull request's CDK diff.
