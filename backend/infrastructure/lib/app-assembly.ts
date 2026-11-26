import * as cdk from "aws-cdk-lib";
import { FindingalphaAdminWebStack } from "./findingalpha-admin-web-stack";
import { FindingalphaPublicWwwStack } from "./findingalpha-public-www-stack";
import { FindingalphaStack } from "./findingalpha-stack";

export function wireFindingalphaApp(
  app: cdk.App,
  env: cdk.Environment = {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
): { backend: FindingalphaStack; adminWeb: FindingalphaAdminWebStack } {
  const bootstrapQualifier = process.env.CDK_BOOTSTRAP_QUALIFIER;
  if (bootstrapQualifier) {
    app.node.setContext("@aws-cdk/core:bootstrapQualifier", bootstrapQualifier);
  }
  const synthesizer = bootstrapQualifier
    ? new cdk.DefaultStackSynthesizer({ qualifier: bootstrapQualifier })
    : undefined;
  new FindingalphaPublicWwwStack(app, "findingalpha-public-www", {
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
    // AdminApiBaseUrl already resolves UseApiCustomDomain inside the API stack.
    cspApiConnectOrigin: cdk.Fn.importValue("findingalpha-AdminApiBaseUrl"),
  });
  adminWeb.addStackDependency(backend);
  // The deployed admin-web stack still imports the execute-api endpoint.
  // This export is removed in the next release after this admin-web stack has deployed.
  backend.exportValue(backend.executeApiEndpoint);
  return { backend, adminWeb };
}
