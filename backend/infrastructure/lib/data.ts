import * as cdk from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as iam from "aws-cdk-lib/aws-iam";
import * as kms from "aws-cdk-lib/aws-kms";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as sqs from "aws-cdk-lib/aws-sqs";

export function defineSharedEncryption(scope: cdk.Stack) {
  const sharedEncryptionKey = new kms.Key(scope, "SharedEncryptionKey", {
    alias: "findingalpha/shared",
    description: "Shared CMK for Lambda env vars, CloudWatch logs, DynamoDB, and the SQS DLQ.",
    enableKeyRotation: true,
    removalPolicy: cdk.RemovalPolicy.RETAIN,
  });
  const region = cdk.Stack.of(scope).region;
  const accountId = cdk.Stack.of(scope).account;
  sharedEncryptionKey.addToResourcePolicy(
    new iam.PolicyStatement({
      sid: "AllowCloudWatchLogsEncryption",
      principals: [new iam.ServicePrincipal(`logs.${region}.amazonaws.com`)],
      actions: ["kms:Encrypt*", "kms:Decrypt*", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:Describe*"],
      resources: ["*"],
      conditions: {
        ArnLike: {
          "kms:EncryptionContext:aws:logs:arn": `arn:aws:logs:${region}:${accountId}:*`,
        },
      },
    }),
  );
  const lambdaDeadLetterQueue = new sqs.Queue(scope, "LambdaDeadLetterQueue", {
    encryption: sqs.QueueEncryption.KMS,
    encryptionMasterKey: sharedEncryptionKey,
    retentionPeriod: cdk.Duration.days(14),
  });
  return { sharedEncryptionKey, lambdaDeadLetterQueue };
}

export function defineTables(scope: cdk.Stack, sharedEncryptionKey: kms.IKey) {
  const recordsTable = new dynamodb.Table(scope, "RecordsTable", {
    tableName: "findingalpha-records",
    partitionKey: { name: "pk", type: dynamodb.AttributeType.STRING },
    sortKey: { name: "sk", type: dynamodb.AttributeType.STRING },
    billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
    encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
    encryptionKey: sharedEncryptionKey,
    removalPolicy: cdk.RemovalPolicy.RETAIN,
    timeToLiveAttribute: "expiresAt",
  });
  recordsTable.addGlobalSecondaryIndex({
    indexName: "gsi1",
    partitionKey: { name: "gsi1pk", type: dynamodb.AttributeType.STRING },
    sortKey: { name: "gsi1sk", type: dynamodb.AttributeType.STRING },
    projectionType: dynamodb.ProjectionType.ALL,
  });
  const auditLogTable = new dynamodb.Table(scope, "AuditLogTable", {
    tableName: "findingalpha-audit-log",
    partitionKey: { name: "pk", type: dynamodb.AttributeType.STRING },
    sortKey: { name: "sk", type: dynamodb.AttributeType.STRING },
    billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
    encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
    encryptionKey: sharedEncryptionKey,
    removalPolicy: cdk.RemovalPolicy.RETAIN,
  });
  return { recordsTable, auditLogTable };
}

export function defineBuckets(scope: cdk.Stack) {
  const account = cdk.Stack.of(scope).account;
  const region = cdk.Stack.of(scope).region;
  const name = (prefix: string) => `${prefix}-${account}-${region}`;
  const locked = {
    blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    enforceSSL: true,
    versioned: true,
    encryption: s3.BucketEncryption.S3_MANAGED,
    removalPolicy: cdk.RemovalPolicy.RETAIN,
  };
  const accessLogsBucket = new s3.Bucket(scope, "AccessLogsBucket", {
    bucketName: name("findingalpha-access-logs"),
    ...locked,
    // Server access logs are written with an ACL. Enforced ownership would drop them.
    objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,
    lifecycleRules: [{ id: "ExpireAccessLogs", expiration: cdk.Duration.days(90) }],
  });
  const dataBucket = new s3.Bucket(scope, "DataBucket", {
    bucketName: name("findingalpha-data"),
    ...locked,
    serverAccessLogsBucket: accessLogsBucket,
    serverAccessLogsPrefix: "data/",
    lifecycleRules: [{ noncurrentVersionExpiration: cdk.Duration.days(30) }],
  });
  const kbBucket = new s3.Bucket(scope, "KbBucket", {
    bucketName: name("findingalpha-kb"),
    ...locked,
    serverAccessLogsBucket: accessLogsBucket,
    serverAccessLogsPrefix: "kb/",
  });
  return { accessLogsBucket, dataBucket, kbBucket };
}
