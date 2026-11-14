---
name: add-engine-job
description: Add a scheduled or manual engine job, its contract row, and its test.
---

# Add an engine job

1. Add the job to `contracts/jobs.json`, including whether a key may start it (`keyRun`).
2. Run `python3 scripts/sync-contracts.py`.
3. Add the handler function and register it in `jobs_handler.py`.
4. Wrap the run with `job_runs.record`.
5. Check its kill switch first. A missing switch means off.
6. Add the schedule in CDK when the job is scheduled. That edit is red. Wait for approval.
7. Add it to the manual-run allow-list only if it is safe to run twice.
8. Write the unit test beside the module.
9. Update `docs/plans/reference.md` section 9.
