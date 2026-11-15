import * as path from "node:path";
import * as cdk from "aws-cdk-lib";
import * as lambda from "aws-cdk-lib/aws-lambda";
import type * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import type * as kms from "aws-cdk-lib/aws-kms";
import type * as s3 from "aws-cdk-lib/aws-s3";
import type * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import type * as sqs from "aws-cdk-lib/aws-sqs";
import { createPythonLambda } from "./constructs/python-lambda";
import type { Parameters } from "./parameters";

const ENGINE_DIR = path.join(__dirname, "..", "..", "lambda", "engine");

export function defineFunctions(
  scope: cdk.Stack,
  input: {
    readonly parameters: Parameters;
    readonly sharedEncryptionKey: kms.IKey;
    readonly lambdaDeadLetterQueue: sqs.Queue;
    readonly recordsTable: dynamodb.Table;
    readonly auditLogTable: dynamodb.Table;
    readonly dataBucket: s3.Bucket;
    readonly kbBucket: s3.Bucket;
  },
) {
  const { parameters, sharedEncryptionKey, lambdaDeadLetterQueue } = input;
  const common = {
    entryDir: ENGINE_DIR,
    environmentEncryptionKey: sharedEncryptionKey,
    logEncryptionKey: sharedEncryptionKey,
    deadLetterQueue: lambdaDeadLetterQueue,
  };
  const sharedEnv: Record<string, string> = {
    RECORDS_TABLE_NAME: input.recordsTable.tableName,
    AUDIT_LOG_TABLE_NAME: input.auditLogTable.tableName,
    DATA_BUCKET_NAME: input.dataBucket.bucketName,
    KB_BUCKET_NAME: input.kbBucket.bucketName,
    INGEST_ENABLED: parameters.ingestEnabled.valueAsString,
    COMMITTEE_ENABLED: parameters.committeeEnabled.valueAsString,
    TRADING_ENABLED: parameters.tradingEnabled.valueAsString,
    LEVERAGE_ENABLED: parameters.leverageEnabled.valueAsString,
    BRIEF_EMAIL_ENABLED: parameters.briefEmailEnabled.valueAsString,
    BROKER_MODE: parameters.brokerMode.valueAsString,
    KB_MAX_RAW_BYTES: parameters.kbMaxRawBytes.valueAsString,
    KB_MAX_RETRIEVALS_PER_MONTH: parameters.kbMaxRetrievalsPerMonth.valueAsString,
    ADMIN_WEB_ORIGIN: cdk.Fn.join("", ["https://", parameters.adminWebDomainName.valueAsString]),
  };
  const adminFn = createPythonLambda(scope, "AdminApiFn", {
    ...common,
    handler: "api_handler.lambda_handler",
    timeout: cdk.Duration.seconds(29),
    memorySize: 512,
    environment: {
      ...sharedEnv,
      PUBLIC_API_WRITES_ENABLED: parameters.publicApiWritesEnabled.valueAsString,
    },
  });
  const engineFn = createPythonLambda(scope, "EngineFn", {
    ...common,
    handler: "jobs_handler.lambda_handler",
    timeout: cdk.Duration.seconds(900),
    memorySize: 2048,
    environment: {
      ...sharedEnv,
      // Literal names. secret.secretName parses the ARN and cuts at the first hyphen.
      ALPACA_SECRET_ID: "findingalpha/alpaca-paper",
      OPENROUTER_SECRET_ID: "findingalpha/openrouter",
      COMMITTEE_ANALYST_MODEL: parameters.committeeAnalystModel.valueAsString,
      COMMITTEE_CHAIR_MODEL: parameters.committeeChairModel.valueAsString,
      MAIL_SENDING_DOMAIN: parameters.mailSendingDomain.valueAsString,
      BRIEF_FROM_LOCAL_PART: parameters.briefFromLocalPart.valueAsString,
      BRIEF_RECIPIENT_EMAIL: parameters.briefRecipientEmail.valueAsString,
      SEC_CONTACT_EMAIL: parameters.secContactEmail.valueAsString,
    },
  });
  input.recordsTable.grantReadWriteData(adminFn);
  input.recordsTable.grantReadWriteData(engineFn);
  input.auditLogTable.grantWriteData(adminFn);
  input.dataBucket.grantRead(adminFn);
  input.dataBucket.grantReadWrite(engineFn);
  input.kbBucket.grantReadWrite(engineFn);
  engineFn.grantInvoke(adminFn);
  adminFn.addEnvironment("ENGINE_FUNCTION_NAME", engineFn.functionName);
  new lambda.EventInvokeConfig(scope, "EngineFnInvokeConfig", {
    function: engineFn,
    retryAttempts: 0,
    maxEventAge: cdk.Duration.minutes(10),
  });
  return { adminFn, engineFn };
}

export function grantEngineSecrets(
  engineFn: lambda.Function,
  secrets: { alpacaPaper: secretsmanager.ISecret; openRouter: secretsmanager.ISecret },
) {
  secrets.alpacaPaper.grantRead(engineFn);
  secrets.openRouter.grantRead(engineFn);
}
