import * as cdk from "aws-cdk-lib";

export function defineOutputs(
  scope: cdk.Stack,
  values: {
    userPoolId: string;
    userPoolClientId: string;
    cognitoDomain: string;
    adminApiBaseUrl: string;
    recordsTableName: string;
    dataBucketName: string;
    kbBucketName: string;
    engineFunctionName: string;
  },
) {
  const pairs: [string, string][] = [
    ["UserPoolId", values.userPoolId],
    ["UserPoolClientId", values.userPoolClientId],
    ["AdminApiBaseUrl", values.adminApiBaseUrl],
    ["RecordsTableName", values.recordsTableName],
    ["DataBucketName", values.dataBucketName],
    ["KbBucketName", values.kbBucketName],
    ["EngineFunctionName", values.engineFunctionName],
  ];
  for (const [key, value] of pairs) {
    new cdk.CfnOutput(scope, key, { value, exportName: `findingalpha-${key}` });
  }
  // Plain output for describe-stacks (Deploy Admin Web). No exportName —
  // nothing imports it, and an export would lock changes to the value.
  new cdk.CfnOutput(scope, "CognitoDomain", {
    value: values.cognitoDomain,
  });
}
