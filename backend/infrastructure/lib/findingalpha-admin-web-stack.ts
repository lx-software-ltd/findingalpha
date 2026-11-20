import * as cdk from "aws-cdk-lib";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";
import { tagStack } from "./tags";

export interface AdminWebStackProps extends cdk.StackProps {
  readonly cspApiConnectOrigin: string;
}

export class FindingalphaAdminWebStack extends cdk.Stack {
  public readonly bucket: s3.Bucket;
  public readonly distribution: cloudfront.Distribution;

  constructor(scope: Construct, id: string, props: AdminWebStackProps) {
    super(scope, id, props);
    tagStack(this);
    const domainName = new cdk.CfnParameter(this, "AdminWebDomainName", {
      type: "String",
      description: "Dashboard hostname.",
    });
    const certificateArn = new cdk.CfnParameter(this, "AdminWebCertificateArn", {
      type: "String",
      description: "ACM certificate in us-east-1.",
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
    const logs = new s3.Bucket(this, "WebLogsBucket", {
      bucketName: `findingalpha-web-logs-${account}-${region}`,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,
      lifecycleRules: [
        { id: "ExpireOldLogs", expiration: cdk.Duration.days(90) },
        { id: "ExpireNoncurrentLogs", noncurrentVersionExpiration: cdk.Duration.days(90) },
      ],
    });
    const bucket = new s3.Bucket(this, "AdminWebBucket", {
      bucketName: `findingalpha-web-${account}-${region}`,
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
    // Import the exported CognitoDomain so CSP tracks prefix vs custom without
    // a separate GitHub variable, and without crossing Fn::If conditions.
    const cognitoOrigin = cdk.Fn.importValue("findingalpha-CognitoDomain");
    const csp = cdk.Fn.join("; ", [
      "default-src 'self'",
      cdk.Fn.join(" ", ["connect-src 'self'", props.cspApiConnectOrigin, cognitoOrigin]),
      "img-src 'self' data:",
      "style-src 'self' 'unsafe-inline'",
      "script-src 'self'",
      "frame-ancestors 'none'",
    ]);
    const headers = new cloudfront.ResponseHeadersPolicy(this, "SecurityHeaders", {
      responseHeadersPolicyName: "findingalpha-admin-security-headers",
      securityHeadersBehavior: {
        contentSecurityPolicy: { contentSecurityPolicy: csp, override: true },
        strictTransportSecurity: { accessControlMaxAge: cdk.Duration.days(365), override: true, includeSubdomains: true },
        contentTypeOptions: { override: true },
        frameOptions: { frameOption: cloudfront.HeadersFrameOption.DENY, override: true },
        referrerPolicy: { referrerPolicy: cloudfront.HeadersReferrerPolicy.NO_REFERRER, override: true },
      },
    });
    this.bucket = bucket;
    const distribution = new cloudfront.Distribution(this, "Distribution", {
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(bucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        responseHeadersPolicy: headers,
        functionAssociations: [{ function: rewrite, eventType: cloudfront.FunctionEventType.VIEWER_REQUEST }],
      },
      domainNames: [domainName.valueAsString],
      certificate: cdk.aws_certificatemanager.Certificate.fromCertificateArn(this, "Cert", certificateArn.valueAsString),
      defaultRootObject: "index.html",
      errorResponses: [{ httpStatus: 404, responseHttpStatus: 200, responsePagePath: "/index.html" }],
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
      throw new Error("AdminWebBucket has no bucket policy; enforceSSL must stay on");
    }
    ownPolicy.addPropertyOverride("PolicyDocument.Statement.1.Sid", "AllowCloudFrontServicePrincipalReadOnly");
    new cdk.CfnOutput(this, "AdminWebBucketName", {
      value: bucket.bucketName,
      exportName: "findingalpha-admin-web-AdminWebBucketName",
    });
    new cdk.CfnOutput(this, "AdminWebDistributionId", {
      value: distribution.distributionId,
      exportName: "findingalpha-admin-web-AdminWebDistributionId",
    });
    new cdk.CfnOutput(this, "AdminWebDistributionDomain", {
      value: distribution.distributionDomainName,
      exportName: "findingalpha-admin-web-AdminWebDistributionDomain",
    });
    new cdk.CfnOutput(this, "AdminWebLoggingBucketName", {
      value: logs.bucketName,
      exportName: "findingalpha-admin-web-AdminWebLoggingBucketName",
    });
  }
}
