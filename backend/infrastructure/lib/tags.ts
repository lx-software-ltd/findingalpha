import * as cdk from "aws-cdk-lib";
import type { IConstruct } from "constructs";

export const ORGANIZATION = "LX Software";
export const PROJECT = "Finding Alpha";

// Applied on the stack so every taggable resource receives both tags,
// including when a test constructs the stack without bin/app.ts.
export function tagStack(scope: IConstruct): void {
  cdk.Tags.of(scope).add("Organization", ORGANIZATION);
  cdk.Tags.of(scope).add("Project", PROJECT);
}
