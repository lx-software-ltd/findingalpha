import * as cdk from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import { FindingalphaAdminWebStack } from "../lib/findingalpha-admin-web-stack";

const ENV = { region: "ap-southeast-1" };
const API_ORIGIN = "https://csp-api-origin";

type Statement = {
  Sid?: string;
  Effect: string;
  Action?: string | string[];
  Principal?: Record<string, unknown>;
  Condition?: Record<string, Record<string, unknown>>;
};

type BucketPolicyResource = {
  Properties: { Bucket: { Ref?: string }; PolicyDocument: { Statement: Statement[] } };
};

describe("findingalpha admin web stack", () => {
  const app = new cdk.App({ context: { "aws:cdk:bundling-stacks": [] } });
  const stack = new FindingalphaAdminWebStack(app, "findingalpha-admin-web", {
    env: ENV,
    cspApiConnectOrigin: API_ORIGIN,
  });
  const template = Template.fromStack(stack);
  const policies = template.findResources("AWS::S3::BucketPolicy") as Record<string, BucketPolicyResource>;
  const bucketLogicalId = stack.getLogicalId(stack.bucket.node.defaultChild as cdk.CfnElement);

  test("the origin bucket has one policy, with TLS deny and the CloudFront read grant", () => {
    const onOrigin = Object.entries(policies).filter(
      ([, policy]) => policy.Properties.Bucket.Ref === bucketLogicalId,
    );
    expect(onOrigin).toHaveLength(1);
    const statements = onOrigin[0][1].Properties.PolicyDocument.Statement;
    const tlsDeny = statements.find(
      (statement) =>
        statement.Effect === "Deny" && statement.Condition?.Bool?.["aws:SecureTransport"] === "false",
    );
    expect(tlsDeny?.Action).toBe("s3:*");
    const oacRead = statements.find((statement) => statement.Sid === "AllowCloudFrontServicePrincipalReadOnly");
    expect(oacRead?.Effect).toBe("Allow");
    expect(oacRead?.Action).toBe("s3:GetObject");
  });

  test("the content security policy allows the API origin and the Cognito origin", () => {
    const headers = template.findResources("AWS::CloudFront::ResponseHeadersPolicy");
    const text = JSON.stringify(headers);
    expect(text).toContain(API_ORIGIN);
    expect(text).toContain("CspCognitoConnectOrigin");
    expect(text).toContain("connect-src 'self'");
  });

  test("both buckets are private and TLS-only", () => {
    const buckets = template.findResources("AWS::S3::Bucket");
    expect(Object.keys(buckets)).toHaveLength(2);
    for (const bucket of Object.values(buckets)) {
      const properties = (bucket as { Properties: Record<string, unknown> }).Properties;
      expect(properties.PublicAccessBlockConfiguration).toEqual({
        BlockPublicAcls: true,
        BlockPublicPolicy: true,
        IgnorePublicAcls: true,
        RestrictPublicBuckets: true,
      });
    }
    expect(Object.keys(policies).length).toBeGreaterThanOrEqual(2);
  });

  test("viewers are redirected to HTTPS", () => {
    template.hasResourceProperties("AWS::CloudFront::Distribution", {
      DistributionConfig: Match.objectLike({
        DefaultCacheBehavior: Match.objectLike({
          ViewerProtocolPolicy: "redirect-to-https",
        }),
      }),
    });
  });
});
