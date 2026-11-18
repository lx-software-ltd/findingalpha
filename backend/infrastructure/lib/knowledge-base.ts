import * as cdk from "aws-cdk-lib";
import * as bedrock from "aws-cdk-lib/aws-bedrock";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import * as iam from "aws-cdk-lib/aws-iam";
import type * as lambda from "aws-cdk-lib/aws-lambda";
import type * as s3 from "aws-cdk-lib/aws-s3";

const PREFIXES = [
  { id: "TheoryDataSource", name: "theory", prefix: "theory/" },
  { id: "FormulaNotesDataSource", name: "formula-notes", prefix: "formula-notes/" },
  { id: "JournalDataSource", name: "journal", prefix: "journal/" },
] as const;

const ENGINE_ACTIONS = [
  "bedrock:Retrieve",
  "bedrock:StartIngestionJob",
  "bedrock:GetIngestionJob",
  "bedrock:ListIngestionJobs",
  "bedrock:ListKnowledgeBaseDocuments",
  "bedrock:StopIngestionJob",
];

/**
 * Managed knowledge base over the theory bucket. No sync schedule: creating
 * the stack ingests nothing. The knowledge base is kept if a later deploy
 * removes it, and deleted if the create itself rolls back. Data sources are
 * not kept; the PDFs in S3 are the source of truth.
 */
export function defineKnowledgeBase(
  scope: cdk.Stack,
  input: { readonly kbBucket: s3.IBucket; readonly engineFn: lambda.Function },
): bedrock.CfnKnowledgeBase {
  const stack = cdk.Stack.of(scope);
  const role = new iam.Role(scope, "KnowledgeBaseRole", {
    assumedBy: new iam.ServicePrincipal("bedrock.amazonaws.com", {
      conditions: {
        StringEquals: { "aws:SourceAccount": stack.account },
        ArnLike: {
          // The knowledge base does not exist yet, so the trust matches the
          // whole family rather than one ARN.
          "aws:SourceArn": stack.formatArn({
            service: "bedrock",
            resource: "knowledge-base",
            resourceName: "*",
            arnFormat: cdk.ArnFormat.SLASH_RESOURCE_NAME,
          }),
        },
      },
    }),
    // Inline, so the policy is part of the role and exists before the
    // knowledge base that references the role is created.
    inlinePolicies: {
      KnowledgeBaseAccess: servicePolicy(input.kbBucket, stack.account),
    },
  });

  const knowledgeBase = new bedrock.CfnKnowledgeBase(scope, "TheoryKnowledgeBase", {
    name: "findingalpha-theory",
    roleArn: role.roleArn,
    knowledgeBaseConfiguration: {
      type: "MANAGED",
      managedKnowledgeBaseConfiguration: { embeddingModelType: "MANAGED" },
    },
  });
  knowledgeBase.applyRemovalPolicy(cdk.RemovalPolicy.RETAIN_ON_UPDATE_OR_DELETE);
  cdk.Tags.of(knowledgeBase).add("mcp-multirag-kb", "true");

  const sources = PREFIXES.map((entry) =>
    connectPrefix(scope, entry.id, entry.name, entry.prefix, knowledgeBase, input.kbBucket, stack.account),
  );
  // One create at a time. Each data source moves from CREATING to
  // AVAILABLE on its own, and the next waits for that to finish.
  for (let index = 1; index < sources.length; index += 1) {
    sources[index].addDependency(sources[index - 1]);
  }
  const sourceIds = Object.fromEntries(PREFIXES.map((entry, index) => [entry.prefix, sources[index].attrDataSourceId]));

  input.engineFn.addEnvironment("KNOWLEDGE_BASE_ID", knowledgeBase.attrKnowledgeBaseId);
  input.engineFn.addEnvironment("KB_DATA_SOURCE_IDS", stack.toJsonString(sourceIds));
  input.engineFn.addToRolePolicy(
    new iam.PolicyStatement({
      actions: ENGINE_ACTIONS,
      resources: [knowledgeBase.attrKnowledgeBaseArn],
    }),
  );

  const rawDataSize = new cloudwatch.Metric({
    namespace: "AWS/Bedrock/KnowledgeBases",
    metricName: "RawDataSize",
    dimensionsMap: {
      KnowledgeBaseId: cdk.Fn.join("", ["knowledge-base/", knowledgeBase.attrKnowledgeBaseId]),
    },
    statistic: "Maximum",
    period: cdk.Duration.hours(1),
  });
  new cloudwatch.Alarm(scope, "KnowledgeBaseRawDataSize", {
    metric: rawDataSize,
    threshold: 2,
    evaluationPeriods: 1,
    comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
    treatMissingData: cloudwatch.TreatMissingData.IGNORE,
    alarmDescription: "Knowledge base raw data is above 2 GB. Published after a sync, in gigabytes.",
  });

  new cdk.CfnOutput(scope, "KnowledgeBaseId", {
    value: knowledgeBase.attrKnowledgeBaseId,
    exportName: "findingalpha-KnowledgeBaseId",
  });
  return knowledgeBase;
}

function servicePolicy(bucket: s3.IBucket, account: string): iam.PolicyDocument {
  return new iam.PolicyDocument({
    statements: [
      new iam.PolicyStatement({
        actions: ["s3:ListBucket"],
        resources: [bucket.bucketArn],
        conditions: { StringEquals: { "aws:ResourceAccount": account } },
      }),
      new iam.PolicyStatement({
        actions: ["s3:GetObject"],
        resources: PREFIXES.map((entry) => bucket.arnForObjects(`${entry.prefix}*`)),
        conditions: { StringEquals: { "aws:ResourceAccount": account } },
      }),
      new iam.PolicyStatement({
        actions: ["cloudwatch:PutMetricData"],
        resources: ["*"],
        conditions: { StringEquals: { "cloudwatch:namespace": "AWS/Bedrock/KnowledgeBases" } },
      }),
    ],
  });
}

function connectPrefix(
  scope: cdk.Stack,
  id: string,
  name: string,
  prefix: string,
  knowledgeBase: bedrock.CfnKnowledgeBase,
  bucket: s3.IBucket,
  account: string,
): bedrock.CfnDataSource {
  return new bedrock.CfnDataSource(scope, id, {
    name,
    knowledgeBaseId: knowledgeBase.attrKnowledgeBaseId,
    dataDeletionPolicy: "DELETE",
    dataSourceConfiguration: {
      type: "MANAGED_KNOWLEDGE_BASE_CONNECTOR",
      managedKnowledgeBaseConnectorConfiguration: {
        connectorParameters: {
          type: "S3",
          version: "1",
          connectionConfiguration: {
            bucketName: bucket.bucketName,
            bucketOwnerAccountId: account,
          },
          filterConfiguration: {
            inclusionPrefixes: [prefix],
            maxFileSizeInMegaBytes: "50",
          },
        },
        deletionProtectionConfiguration: {
          deletionProtectionStatus: "ENABLED",
          deletionProtectionThreshold: 15,
        },
      },
    },
    // Managed embedding rejects chunkingConfiguration. Omitting this
    // block applies the service defaults: 300 tokens with 20% overlap,
    // and Smart Parsing.
  });
}
