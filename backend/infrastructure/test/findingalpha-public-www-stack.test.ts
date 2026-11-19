import * as cdk from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import { FindingalphaPublicWwwStack } from "../lib/findingalpha-public-www-stack";
import { tagReport } from "./resource-tags";

const ENV = { region: "ap-southeast-1" };

type Statement = {
  Sid?: string;
  Effect: string;
  Action?: string | string[];
  Condition?: Record<string, Record<string, unknown>>;
};

type BucketPolicyResource = {
  Properties: { Bucket: { Ref?: string }; PolicyDocument: { Statement: Statement[] } };
};

describe("findingalpha public www stack", () => {
  const app = new cdk.App({ context: { "aws:cdk:bundling-stacks": [] } });
  const stack = new FindingalphaPublicWwwStack(app, "findingalpha-public-www", {
    env: ENV,
  });
  const template = Template.fromStack(stack);

  test("every taggable resource carries the organization and the project", () => {
    const report = tagReport(app, stack);
    expect(report.missing).toEqual([]);
    expect(report.untaggedTypes).toEqual([
      "AWS::CloudFront::OriginAccessControl",
      "AWS::CloudFront::ResponseHeadersPolicy",
      "AWS::S3::BucketPolicy",
    ]);
  });

  test("the origin bucket has TLS deny and the CloudFront read grant", () => {
    const policies = template.findResources("AWS::S3::BucketPolicy") as Record<
      string,
      BucketPolicyResource
    >;
    const bucketLogicalId = stack.getLogicalId(stack.bucket.node.defaultChild as cdk.CfnElement);
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

  test("both buckets are private", () => {
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
  });

  test("viewers are redirected to HTTPS and the CSP stays tight", () => {
    template.hasResourceProperties("AWS::CloudFront::Distribution", {
      DistributionConfig: Match.objectLike({
        DefaultCacheBehavior: Match.objectLike({
          ViewerProtocolPolicy: "redirect-to-https",
        }),
      }),
    });
    const headers = template.findResources("AWS::CloudFront::ResponseHeadersPolicy");
    const text = JSON.stringify(headers);
    expect(text).toContain("frame-ancestors 'none'");
    expect(text).toContain("object-src 'none'");
    expect(text).not.toContain("googletagmanager");
  });

  test("exports the bucket and distribution ids the deploy script reads", () => {
    template.hasOutput("PublicWebsiteBucketName", {});
    template.hasOutput("PublicWebsiteDistributionId", {});
    template.hasOutput("PublicWebsiteDistributionDomain", {});
  });
});
