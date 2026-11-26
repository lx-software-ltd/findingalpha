import * as path from "node:path";
import * as cdk from "aws-cdk-lib";
import { HttpLambdaAuthorizer, HttpLambdaResponseType } from "aws-cdk-lib/aws-apigatewayv2-authorizers";
import * as iam from "aws-cdk-lib/aws-iam";
import type * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import type * as kms from "aws-cdk-lib/aws-kms";
import type * as sqs from "aws-cdk-lib/aws-sqs";
import { createPythonLambda } from "./constructs/python-lambda";

const AUTHORIZER_DIR = path.join(__dirname, "..", "..", "lambda", "public_api_authorizer");

/** Key authorizer. It can read and update only APIKEY#* rows, and nothing else in the table. */
export function defineKeyAuthorizer(
  scope: cdk.Stack,
  input: {
    readonly recordsTable: dynamodb.Table;
    readonly sharedEncryptionKey: kms.IKey;
    readonly lambdaDeadLetterQueue: sqs.Queue;
  },
) {
  const fn = createPythonLambda(scope, "PublicApiKeyAuthorizerFn", {
    entryDir: AUTHORIZER_DIR,
    handler: "handler.lambda_handler",
    timeout: cdk.Duration.seconds(5),
    memorySize: 256,
    environment: { RECORDS_TABLE_NAME: input.recordsTable.tableName },
    environmentEncryptionKey: input.sharedEncryptionKey,
    logEncryptionKey: input.sharedEncryptionKey,
    deadLetterQueue: input.lambdaDeadLetterQueue,
  });
  input.lambdaDeadLetterQueue.grantSendMessages(fn);
  // UpdateItem on a customer-managed key needs GenerateDataKey as well as Decrypt.
  input.sharedEncryptionKey.grantEncryptDecrypt(fn);
  const role = fn.role;
  if (role) {
    new iam.Policy(scope, "PublicApiKeyAuthorizerTable", {
      roles: [role],
      statements: [
        new iam.PolicyStatement({
          actions: ["dynamodb:GetItem", "dynamodb:UpdateItem"],
          resources: [input.recordsTable.tableArn],
          conditions: {
            "ForAllValues:StringLike": {
              "dynamodb:LeadingKeys": ["APIKEY#*"],
            },
          },
        }),
      ],
    });
  }
  const authorizer = new HttpLambdaAuthorizer("public-api-key", fn, {
    responseTypes: [HttpLambdaResponseType.SIMPLE],
    // A listed identity source that is missing makes API Gateway return 401
    // without calling the Lambda. Callers send one credential header, not
    // both, so neither header is an identity source. Caching is off, so a
    // verdict cannot be reused for another token, scheme, or address.
    identitySource: ["$context.identity.sourceIp"],
    resultsCacheTtl: cdk.Duration.seconds(0),
  });
  return { authorizer, fn };
}
