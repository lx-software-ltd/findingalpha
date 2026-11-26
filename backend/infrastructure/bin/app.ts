import * as cdk from "aws-cdk-lib";
import { CheckovSuppressionAspect } from "../lib/constructs/checkov-suppressions";
import { wireFindingalphaApp } from "../lib/app-assembly";
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

wireFindingalphaApp(app);

cdk.Aspects.of(app).add(new CheckovSuppressionAspect());
