import * as cdk from "aws-cdk-lib";
import { CheckovSuppressionAspect } from "../lib/constructs/checkov-suppressions";
import { FindingalphaAdminWebStack } from "../lib/findingalpha-admin-web-stack";
import { FindingalphaPublicWwwStack } from "../lib/findingalpha-public-www-stack";
import { FindingalphaStack } from "../lib/findingalpha-stack";
import { ORGANIZATION, PROJECT } from "../lib/tags";

const app = new cdk.App();

const COMMON_TAGS: Record<string, string> = {
  Organization: ORGANIZATION,
  Project: PROJECT,
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

const publicWww = new FindingalphaPublicWwwStack(app, "findingalpha-public-www", {
  description: "findingalpha public logo website (S3 + CloudFront).",
  env,
  synthesizer,
});

const backend = new FindingalphaStack(app, "findingalpha", {
  description: "findingalpha backend: Cognito, DynamoDB, S3, the HTTP API, and the knowledge base.",
  env,
  synthesizer,
});

const adminWeb = new FindingalphaAdminWebStack(app, "findingalpha-admin-web", {
  description: "findingalpha admin dashboard delivery.",
  env,
  synthesizer,
  cspApiConnectOrigin: backend.httpApiEndpoint,
});

cdk.Aspects.of(app).add(new CheckovSuppressionAspect());
