import * as cdk from "aws-cdk-lib";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";
import { tagStack } from "./tags";

export class FindingalphaPublicWwwStack extends cdk.Stack {
  public readonly bucket: s3.Bucket;
  public readonly distribution: cloudfront.Distribution;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);
    tagStack(this);

    const domainName = new cdk.CfnParameter(this, "PublicWebsiteDomainName", {
      type: "String",
      description: "Public website hostname (CloudFront alias).",
    });
    const certificateArn = new cdk.CfnParameter(this, "PublicWebsiteCertificateArn", {
      type: "String",
      description: "ACM certificate in us-east-1 for the public website hostname.",
    });
    const wafArn = new cdk.CfnParameter(this, "WafWebAclArn", {
      type: "String",
      default: "",
      description: "Optional global web ACL. Empty disables it.",
    });
    const useWaf = new cdk.CfnCondition(this, "UseWaf", {
      expression: cdk.Fn.conditionNot(cdk.Fn.conditionEquals(wafArn.valueAsString, "")),
    });

    const account = cdk.Stack.of(this).account;
    const region = cdk.Stack.of(this).region;

    const logs = new s3.Bucket(this, "PublicWwwLogsBucket", {
      bucketName: `findingalpha-public-www-logs-${account}-${region}`,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,
      lifecycleRules: [{ id: "ExpireOldLogs", expiration: cdk.Duration.days(90) }],
    });

    const bucket = new s3.Bucket(this, "PublicWwwBucket", {
      bucketName: `findingalpha-public-www-${account}-${region}`,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      serverAccessLogsBucket: logs,
      serverAccessLogsPrefix: "web/",
    });

    const rewrite = new cloudfront.Function(this, "SpaRewrite", {
      code: cloudfront.FunctionCode.fromInline(`function handler(event) {
  var request = event.request;
  var uri = request.uri;
  if (uri.startsWith('/assets/')) return request;
  if (uri.indexOf('.') === -1) {
    request.uri = '/index.html';
  }
  return request;
}`),
    });

    const csp = [
      "default-src 'self'",
      "script-src 'self'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data:",
      "font-src 'self'",
      "connect-src 'self'",
      "object-src 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      "frame-ancestors 'none'",
    ].join("; ");

    const headers = new cloudfront.ResponseHeadersPolicy(this, "SecurityHeaders", {
      responseHeadersPolicyName: "findingalpha-public-www-security-headers",
      securityHeadersBehavior: {
        contentSecurityPolicy: { contentSecurityPolicy: csp, override: true },
        strictTransportSecurity: {
          accessControlMaxAge: cdk.Duration.days(365),
          override: true,
          includeSubdomains: true,
        },
        contentTypeOptions: { override: true },
        frameOptions: { frameOption: cloudfront.HeadersFrameOption.DENY, override: true },
        referrerPolicy: {
          referrerPolicy: cloudfront.HeadersReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN,
          override: true,
        },
      },
      customHeadersBehavior: {
        customHeaders: [
          {
            header: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
            override: true,
          },
        ],
      },
    });

    this.bucket = bucket;
    const distribution = new cloudfront.Distribution(this, "Distribution", {
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(bucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
        responseHeadersPolicy: headers,
        functionAssociations: [{ function: rewrite, eventType: cloudfront.FunctionEventType.VIEWER_REQUEST }],
      },
      domainNames: [domainName.valueAsString],
      certificate: cdk.aws_certificatemanager.Certificate.fromCertificateArn(
        this,
        "Cert",
        certificateArn.valueAsString,
      ),
      defaultRootObject: "index.html",
      errorResponses: [
        { httpStatus: 403, responseHttpStatus: 200, responsePagePath: "/index.html", ttl: cdk.Duration.minutes(5) },
        { httpStatus: 404, responseHttpStatus: 200, responsePagePath: "/index.html", ttl: cdk.Duration.minutes(5) },
      ],
      logBucket: logs,
      logFilePrefix: "cloudfront/",
    });
    this.distribution = distribution;

    const cfnDistribution = distribution.node.defaultChild as cloudfront.CfnDistribution;
    cfnDistribution.addPropertyOverride(
      "DistributionConfig.WebACLId",
      cdk.Fn.conditionIf(useWaf.logicalId, wafArn.valueAsString, cdk.Aws.NO_VALUE),
    );

    const ownPolicy = bucket.policy?.node.defaultChild as s3.CfnBucketPolicy | undefined;
    if (!ownPolicy) {
      throw new Error("PublicWwwBucket has no bucket policy; enforceSSL must stay on");
    }
    ownPolicy.addPropertyOverride("PolicyDocument.Statement.1.Sid", "AllowCloudFrontServicePrincipalReadOnly");

    new cdk.CfnOutput(this, "PublicWebsiteBucketName", {
      value: bucket.bucketName,
      exportName: "findingalpha-public-www-PublicWebsiteBucketName",
    });
    new cdk.CfnOutput(this, "PublicWebsiteDistributionId", {
      value: distribution.distributionId,
      exportName: "findingalpha-public-www-PublicWebsiteDistributionId",
    });
    new cdk.CfnOutput(this, "PublicWebsiteDistributionDomain", {
      value: distribution.distributionDomainName,
      exportName: "findingalpha-public-www-PublicWebsiteDistributionDomain",
    });
    new cdk.CfnOutput(this, "PublicWebsiteLoggingBucketName", {
      value: logs.bucketName,
      exportName: "findingalpha-public-www-PublicWebsiteLoggingBucketName",
    });
  }
}
