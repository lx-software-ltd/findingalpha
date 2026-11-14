# Security

Sign-in is a Cognito user pool. Self sign-up is off. MFA is required
(TOTP). The app client has no secret and uses the authorization code
grant. Google is a federated identity provider. The pre sign-up and
pre token triggers refuse any email that is not on the allow-list,
except the bootstrap user who is already in the `admin` group.

The HTTP API authorizes with the Cognito ID token. The audience is the
app client id. `/health` is the only route without that authorizer.
CORS allows the dashboard origin only. Stage throttle is 50 requests
per second with a burst of 100. Access logs go to an encrypted log
group. One API Gateway invoke permission covers every route.

`AdminApiFn` cannot read the broker or model secrets. `EngineFn` can.
Both secrets are created empty and retained. Their names are literals
in the function environment, not values.

Kill-switch parameters default to `false`. The engine also requires the
same flag on the settings row. Either side missing means the switch is
off.

Buckets block public access, require TLS, and are versioned. Tables,
the key, the buckets, the user pool and the secrets are retained on
stack delete.

The dashboard is a private S3 bucket behind CloudFront. The bucket
policy is the one CDK creates for the origin: a TLS deny and one
CloudFront read grant. The response headers policy sets a content
security policy that allows the API origin and the Cognito origin.
Viewer requests redirect to HTTPS. A web ACL is attached only when its
ARN parameter is set.
