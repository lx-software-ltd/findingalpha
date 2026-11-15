import * as cdk from "aws-cdk-lib";
import { CheckovSuppressionAspect } from "../lib/constructs/checkov-suppressions";
import { FindingalphaAdminWebStack } from "../lib/findingalpha-admin-web-stack";
import { FindingalphaStack } from "../lib/findingalpha-stack";

const app = new cdk.App();

const COMMON_TAGS: Record<string, string> = {
  Organization: "findingalpha",
  Repository: "findingalpha",
  Environment: "production",
  ManagedBy: "CDK",
};

for (const [key, value] of Object.entries(COMMON_TAGS)) {
  cdk.Tags.of(app).add(key, value);
}

const bootstrapQualifier = process.env.CDK_BOOTSTRAP_QUALIFIER;
if (bootstrapQualifier) {
  app.node.setContext("@aws-cdk/core:bootstrapQualifier", bootstrapQualifier);
}

const synthesizer = bootstrapQualifier
  ? new cdk.DefaultStackSynthesizer({ qualifier: bootstrapQualifier })
  : undefined;

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION,
};

const backend = new FindingalphaStack(app, "findingalpha", {
  description: "findingalpha backend: Cognito, DynamoDB, S3, and the HTTP API.",
  env,
  synthesizer,
});
cdk.Tags.of(backend).add("Project", "findingalpha");

const adminWeb = new FindingalphaAdminWebStack(app, "findingalpha-admin-web", {
  description: "findingalpha admin dashboard delivery.",
  env,
  synthesizer,
  cspApiConnectOrigin: backend.httpApiEndpoint,
});
cdk.Tags.of(adminWeb).add("Project", "findingalpha");

cdk.Aspects.of(app).add(new CheckovSuppressionAspect());
