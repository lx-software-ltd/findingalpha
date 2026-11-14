import * as cdk from "aws-cdk-lib";
import * as kms from "aws-cdk-lib/aws-kms";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";

/** Empty secrets. The engine treats a secret without the expected JSON fields as not configured. */
export function defineSecrets(scope: cdk.Stack, key: kms.IKey) {
  const alpacaPaper = new secretsmanager.Secret(scope, "AlpacaPaperSecret", {
    secretName: "findingalpha/alpaca-paper",
    encryptionKey: key,
    removalPolicy: cdk.RemovalPolicy.RETAIN,
  });
  const openRouter = new secretsmanager.Secret(scope, "OpenRouterSecret", {
    secretName: "findingalpha/openrouter",
    encryptionKey: key,
    removalPolicy: cdk.RemovalPolicy.RETAIN,
  });
  return { alpacaPaper, openRouter };
}
