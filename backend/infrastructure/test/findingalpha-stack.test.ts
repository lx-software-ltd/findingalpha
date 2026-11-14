import * as cdk from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import { FindingalphaAdminWebStack } from "../lib/findingalpha-admin-web-stack";
import { FindingalphaStack } from "../lib/findingalpha-stack";

const ENV = { account: "123456789012", region: "ap-southeast-1" };

function backend() {
  const app = new cdk.App({ context: { "aws:cdk:bundling-stacks": [] } });
  const stack = new FindingalphaStack(app, "findingalpha", { env: ENV });
  return Template.fromStack(stack);
}

test("tables keep keys, encryption, recovery and retain", () => {
  const synthesized = backend();
  for (const name of ["findingalpha-records", "findingalpha-audit-log"]) {
    synthesized.hasResourceProperties("AWS::DynamoDB::Table", {
      TableName: name,
      BillingMode: "PAY_PER_REQUEST",
      PointInTimeRecoverySpecification: { PointInTimeRecoveryEnabled: true },
      SSESpecification: Match.objectLike({ SSEType: "KMS" }),
      KeySchema: Match.arrayWith([
        Match.objectLike({ AttributeName: "pk", KeyType: "HASH" }),
        Match.objectLike({ AttributeName: "sk", KeyType: "RANGE" }),
      ]),
      DeletionPolicy: Match.absent(),
    });
  }
  const tables = synthesized.findResources("AWS::DynamoDB::Table");
  for (const resource of Object.values(tables)) {
    expect(resource.DeletionPolicy).toBe("Retain");
  }
  synthesized.hasResourceProperties("AWS::DynamoDB::Table", {
    TableName: "findingalpha-records",
    TimeToLiveSpecification: { AttributeName: "expiresAt", Enabled: true },
  });
});

test("every bucket blocks public access and requires TLS", () => {
  const synthesized = backend();
  const buckets = synthesized.findResources("AWS::S3::Bucket");
  expect(Object.keys(buckets).length).toBeGreaterThanOrEqual(3);
  for (const resource of Object.values(buckets)) {
    const access = resource.Properties.PublicAccessBlockConfiguration;
    expect(access.BlockPublicAcls).toBe(true);
    expect(access.BlockPublicPolicy).toBe(true);
    expect(access.IgnorePublicAcls).toBe(true);
    expect(access.RestrictPublicBuckets).toBe(true);
  }
  const policies = synthesized.findResources("AWS::S3::BucketPolicy");
  const documents = JSON.stringify(policies);
  expect(documents).toContain("aws:SecureTransport");
  expect(Object.keys(policies).length).toBe(Object.keys(buckets).length);
});

test("user pool requires MFA and has both triggers", () => {
  const synthesized = backend();
  synthesized.hasResourceProperties("AWS::Cognito::UserPool", {
    MfaConfiguration: "ON",
    AdminCreateUserConfig: { AllowAdminCreateUserOnly: true },
    LambdaConfig: Match.objectLike({
      PreSignUp: Match.anyValue(),
      PreTokenGeneration: Match.anyValue(),
    }),
  });
  synthesized.hasResourceProperties("AWS::Cognito::UserPoolClient", {
    GenerateSecret: false,
    AllowedOAuthFlows: ["code"],
    CallbackURLs: Match.anyValue(),
  });
});

test("secrets stay out of the API function and kill switches default off", () => {
  const synthesized = backend();
  synthesized.hasParameter("GoogleClientSecret", { NoEcho: true });
  synthesized.hasParameter("AdminBootstrapTempPassword", { NoEcho: true });
  for (const name of [
    "IngestEnabled",
    "CommitteeEnabled",
    "TradingEnabled",
    "LeverageEnabled",
    "BriefEmailEnabled",
    "PublicApiWritesEnabled",
  ]) {
    synthesized.hasParameter(name, { Default: "false", AllowedValues: ["true", "false"] });
  }
  synthesized.hasParameter("BrokerMode", { AllowedValues: ["paper"], Default: "paper" });
  synthesized.hasResourceProperties("AWS::SecretsManager::Secret", { Name: "findingalpha/alpaca-paper" });
  synthesized.hasResourceProperties("AWS::SecretsManager::Secret", { Name: "findingalpha/openrouter" });

  const functions = synthesized.findResources("AWS::Lambda::Function");
  const roles = synthesized.findResources("AWS::IAM::Policy");
  const roleText = JSON.stringify(roles);
  const engine = Object.values(functions).find((fn) =>
    JSON.stringify(fn).includes("findingalpha/alpaca-paper"),
  );
  const api = Object.values(functions).find((fn) =>
    JSON.stringify(fn).includes("PUBLIC_API_WRITES_ENABLED"),
  );
  expect(engine).toBeDefined();
  expect(api).toBeDefined();
  expect(roleText).toContain("secretsmanager:GetSecretValue");
  expect(JSON.stringify(api)).not.toContain("secretsmanager:GetSecretValue");
});

test("only health is open and the tick is a schedule", () => {
  const synthesized = backend();
  const routes = synthesized.findResources("AWS::ApiGatewayV2::Route");
  for (const resource of Object.values(routes)) {
    const key = resource.Properties.RouteKey as string;
    if (key === "GET /health") {
      expect(resource.Properties.AuthorizationType).toBe("NONE");
    } else {
      expect(resource.Properties.AuthorizationType).toBe("JWT");
    }
  }
  const permissions = synthesized.findResources("AWS::Lambda::Permission");
  const apiGateway = Object.values(permissions).filter((permission) =>
    JSON.stringify(permission.Properties.Principal).includes("apigateway.amazonaws.com"),
  );
  expect(apiGateway).toHaveLength(1);
  expect(Object.keys(synthesized.findResources("AWS::Scheduler::Schedule"))).toHaveLength(1);
  expect(Object.keys(synthesized.findResources("AWS::Events::Rule"))).toHaveLength(0);
});

test("web stack redirects to HTTPS and names both origins in the CSP", () => {
  const app = new cdk.App({ context: { "aws:cdk:bundling-stacks": [] } });
  const stack = new FindingalphaAdminWebStack(app, "findingalpha-admin-web", {
    env: ENV,
    cspApiConnectOrigin: "https://example.execute-api.ap-southeast-1.amazonaws.com",
  });
  const synthesized = Template.fromStack(stack);
  const policies = synthesized.findResources("AWS::S3::BucketPolicy");
  const bucketId = stack.getLogicalId(stack.bucket.node.defaultChild as cdk.CfnElement);
  const onOrigin = Object.values(policies).filter(
    (policy) => (policy.Properties.Bucket as { Ref: string }).Ref === bucketId,
  );
  expect(onOrigin).toHaveLength(1);
  synthesized.hasResourceProperties("AWS::CloudFront::Distribution", {
    DistributionConfig: Match.objectLike({
      DefaultCacheBehavior: Match.objectLike({ ViewerProtocolPolicy: "redirect-to-https" }),
    }),
  });
  const headers = JSON.stringify(synthesized.findResources("AWS::CloudFront::ResponseHeadersPolicy"));
  expect(headers).toContain("example.execute-api.ap-southeast-1.amazonaws.com");
  expect(headers).toContain("CspCognitoConnectOrigin");
});
