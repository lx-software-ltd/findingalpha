# CDK parameter file

`production.json` holds defaults that are the same in every account.
Values that name the owner, the domain, or a certificate come from the
GitHub `production` environment. See `docs/plans/reference.md` section 3.

Keys are `<stack>:<Parameter>`. Allowed prefixes are `findingalpha:` and
`findingalpha-admin-web:`. `scripts/deploy/cdk-params.sh` rejects any
other key.
