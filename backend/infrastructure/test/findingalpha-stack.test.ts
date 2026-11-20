import * as cdk from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import { FindingalphaStack } from "../lib/findingalpha-stack";
import { readTag, tagReport } from "./resource-tags";

const ENV = { region: "ap-southeast-1" };

const KILL_SWITCHES = [
  "IngestEnabled",
  "CommitteeEnabled",
  "TradingEnabled",
  "LeverageEnabled",
  "BriefEmailEnabled",
  "PublicApiWritesEnabled",
];

type CfnResource = {
  DeletionPolicy?: string;
  UpdateReplacePolicy?: string;
  Condition?: string;
  DependsOn?: string | string[];
  Properties: Record<string, unknown>;
};

function dependencyList(resource: CfnResource): string[] {
  const depends = resource.DependsOn;
  if (Array.isArray(depends)) return depends;
  return depends ? [depends] : [];
}

let synthesized: Template;
let app: cdk.App;
let stack: FindingalphaStack;

beforeAll(() => {
  app = new cdk.App({ context: { "aws:cdk:bundling-stacks": [] } });
  stack = new FindingalphaStack(app, "findingalpha", { env: ENV });
  synthesized = Template.fromStack(stack);
});

function resources(type: string): Record<string, CfnResource> {
  return synthesized.findResources(type) as Record<string, CfnResource>;
}

function roleIdForHandler(handler: string): string {
  for (const resource of Object.values(resources("AWS::Lambda::Function"))) {
    if (resource.Properties.Handler !== handler) {
      continue;
    }
    const role = resource.Properties.Role as { Ref?: string; "Fn::GetAtt"?: string[] };
    if (role.Ref) {
      return role.Ref;
    }
    if (role["Fn::GetAtt"]) {
      return role["Fn::GetAtt"][0];
    }
  }
  throw new Error(`no role for ${handler}`);
}

function policyTextForRole(roleId: string): string {
  const docs: unknown[] = [];
  for (const policy of Object.values(resources("AWS::IAM::Policy"))) {
    const roles = (policy.Properties.Roles as { Ref?: string }[]) ?? [];
    if (roles.some((role) => role.Ref === roleId)) {
      docs.push(policy.Properties.PolicyDocument);
    }
  }
  return JSON.stringify(docs);
}

function secretLogicalId(name: string): string {
  for (const [id, secret] of Object.entries(resources("AWS::SecretsManager::Secret"))) {
    if (secret.Properties.Name === name) {
      return id;
    }
  }
  throw new Error(`no secret named ${name}`);
}

describe("findingalpha stack", () => {
  test("every taggable resource carries the organization and the project", () => {
    const report = tagReport(app, stack);
    expect(report.missing).toEqual([]);
    // These types have no tag property in CloudFormation. A new type must
    // carry both tags or be added here on purpose.
    expect(report.untaggedTypes).toEqual([
      "AWS::ApiGatewayV2::ApiMapping",
      "AWS::ApiGatewayV2::Authorizer",
      "AWS::ApiGatewayV2::Integration",
      "AWS::ApiGatewayV2::Route",
      "AWS::Bedrock::DataSource",
      "AWS::Cognito::UserPoolClient",
      "AWS::Cognito::UserPoolDomain",
      "AWS::Cognito::UserPoolGroup",
      "AWS::Cognito::UserPoolIdentityProvider",
      "AWS::IAM::Policy",
      "AWS::KMS::Alias",
      "AWS::Lambda::EventInvokeConfig",
      "AWS::Lambda::Permission",
      "AWS::Logs::ResourcePolicy",
      "AWS::S3::BucketPolicy",
      "AWS::Scheduler::Schedule",
    ]);
  });

  test("tables keep keys, on-demand billing, recovery, encryption, and retain", () => {
    synthesized.hasResourceProperties("AWS::DynamoDB::Table", {
      TableName: "findingalpha-records",
      BillingMode: "PAY_PER_REQUEST",
      KeySchema: [
        { AttributeName: "pk", KeyType: "HASH" },
        { AttributeName: "sk", KeyType: "RANGE" },
      ],
      PointInTimeRecoverySpecification: { PointInTimeRecoveryEnabled: true },
      SSESpecification: Match.objectLike({ SSEEnabled: true, SSEType: "KMS" }),
      TimeToLiveSpecification: { AttributeName: "expiresAt", Enabled: true },
      GlobalSecondaryIndexes: [
        Match.objectLike({
          IndexName: "gsi1",
          KeySchema: [
            { AttributeName: "gsi1pk", KeyType: "HASH" },
            { AttributeName: "gsi1sk", KeyType: "RANGE" },
          ],
          Projection: { ProjectionType: "ALL" },
        }),
      ],
    });
    synthesized.hasResourceProperties("AWS::DynamoDB::Table", {
      TableName: "findingalpha-audit-log",
      BillingMode: "PAY_PER_REQUEST",
      KeySchema: [
        { AttributeName: "pk", KeyType: "HASH" },
        { AttributeName: "sk", KeyType: "RANGE" },
      ],
      PointInTimeRecoverySpecification: { PointInTimeRecoveryEnabled: true },
      SSESpecification: Match.objectLike({ SSEEnabled: true, SSEType: "KMS" }),
    });
    const tables = resources("AWS::DynamoDB::Table");
    expect(Object.keys(tables)).toHaveLength(2);
    for (const table of Object.values(tables)) {
      expect(table.DeletionPolicy).toBe("Retain");
    }
    const audit = Object.values(tables).find((table) => table.Properties.TableName === "findingalpha-audit-log");
    expect(audit?.Properties.GlobalSecondaryIndexes).toBeUndefined();
  });

  test("every bucket blocks public access, requires TLS, and is retained", () => {
    const buckets = resources("AWS::S3::Bucket");
    expect(Object.keys(buckets).length).toBeGreaterThanOrEqual(3);
    for (const bucket of Object.values(buckets)) {
      expect(bucket.Properties.PublicAccessBlockConfiguration).toEqual({
        BlockPublicAcls: true,
        BlockPublicPolicy: true,
        IgnorePublicAcls: true,
        RestrictPublicBuckets: true,
      });
      expect(bucket.DeletionPolicy).toBe("Retain");
      expect(bucket.Properties.VersioningConfiguration).toEqual({ Status: "Enabled" });
    }
    const policies = resources("AWS::S3::BucketPolicy");
    expect(Object.keys(policies)).toHaveLength(Object.keys(buckets).length);
    for (const policy of Object.values(policies)) {
      const statements = (policy.Properties.PolicyDocument as { Statement: Record<string, unknown>[] }).Statement;
      const tlsDeny = statements.find((statement) => {
        const condition = statement.Condition as { Bool?: Record<string, string> } | undefined;
        return statement.Effect === "Deny" && condition?.Bool?.["aws:SecureTransport"] === "false";
      });
      expect(tlsDeny).toBeDefined();
    }
  });

  test("user pool does not require MFA, refuses self sign-up, and sets both triggers", () => {
    synthesized.hasResourceProperties("AWS::Cognito::UserPool", {
      UserPoolName: "findingalpha-admin-user-pool",
      MfaConfiguration: "OFF",
      AdminCreateUserConfig: Match.objectLike({ AllowAdminCreateUserOnly: true }),
      LambdaConfig: Match.objectLike({
        PreSignUp: Match.anyValue(),
        PreTokenGeneration: Match.anyValue(),
      }),
    });
    const pool = Object.values(resources("AWS::Cognito::UserPool"))[0];
    expect(pool.DeletionPolicy).toBe("Retain");
    expect(JSON.stringify(synthesized.toJSON())).not.toContain("adminCreateUser");
  });

  test("app client has no secret, uses the code grant, and builds the callback from the parameter", () => {
    const clients = resources("AWS::Cognito::UserPoolClient");
    expect(Object.keys(clients)).toHaveLength(1);
    const client = Object.values(clients)[0].Properties;
    expect(client.GenerateSecret).toBeFalsy();
    expect(client.AllowedOAuthFlows).toEqual(["code"]);
    expect(client.ClientName).toBe("findingalpha-admin-spa-client");
    expect(client.SupportedIdentityProviders).toHaveLength(1);
    expect(JSON.stringify(client.SupportedIdentityProviders)).toContain("GoogleProvider");
    expect(JSON.stringify(client.SupportedIdentityProviders)).not.toContain("COGNITO");
    expect(JSON.stringify(client.ExplicitAuthFlows ?? [])).not.toContain("PASSWORD");
    expect(JSON.stringify(client.ExplicitAuthFlows ?? [])).not.toContain("SRP");
    const callbacks = JSON.stringify(client.CallbackURLs);
    expect(callbacks).toContain("AdminWebDomainName");
    expect(callbacks).toContain("/auth/callback");
  });

  test("secret parameters are NoEcho and kill switches default off", () => {
    synthesized.hasParameter("GoogleClientSecret", { NoEcho: true });
    expect(synthesized.findParameters("AdminBootstrapEmail")).toEqual({});
    expect(synthesized.findParameters("AdminBootstrapTempPassword")).toEqual({});
    synthesized.hasParameter("ApiCustomDomainName", { Type: "String", Default: "" });
    synthesized.hasParameter("ApiCustomDomainCertificateArn", { Type: "String", Default: "" });
    for (const name of KILL_SWITCHES) {
      synthesized.hasParameter(name, {
        Type: "String",
        Default: "false",
        AllowedValues: ["true", "false"],
      });
    }
    synthesized.hasParameter("BrokerMode", {
      Type: "String",
      Default: "paper",
      AllowedValues: ["paper"],
    });
  });

  test("only EngineFn can read the broker and model secrets", () => {
    const alpaca = secretLogicalId("findingalpha/alpaca-paper");
    const openrouter = secretLogicalId("findingalpha/openrouter");
    const admin = policyTextForRole(roleIdForHandler("api_handler.lambda_handler"));
    const engine = policyTextForRole(roleIdForHandler("jobs_handler.lambda_handler"));
    for (const marker of [alpaca, openrouter, "findingalpha/alpaca-paper", "findingalpha/openrouter"]) {
      expect(admin).not.toContain(marker);
    }
    expect(engine).toContain(alpaca);
    expect(engine).toContain(openrouter);
    expect(engine).toContain("secretsmanager:GetSecretValue");
    const engineFn = Object.values(resources("AWS::Lambda::Function")).find(
      (fn) => fn.Properties.Handler === "jobs_handler.lambda_handler",
    );
    const variables = (engineFn?.Properties.Environment as { Variables: Record<string, string> }).Variables;
    expect(variables.ALPACA_SECRET_ID).toBe("findingalpha/alpaca-paper");
    expect(variables.OPENROUTER_SECRET_ID).toBe("findingalpha/openrouter");
  });

  test("dashboard routes use the JWT authorizer and public routes use the key", () => {
    const keyRoutes = new Set([
      "GET /public",
      "GET /public/{proxy+}",
      "PUT /public/{proxy+}",
      "POST /public/{proxy+}",
    ]);
    const routes = resources("AWS::ApiGatewayV2::Route");
    const keys = Object.values(routes).map((route) => String(route.Properties.RouteKey));
    expect(keys).toEqual(expect.arrayContaining(["GET /health", "GET /me", "GET /api-keys", "GET /public"]));
    for (const route of Object.values(routes)) {
      const routeKey = String(route.Properties.RouteKey);
      if (routeKey === "GET /health") {
        expect(route.Properties.AuthorizationType ?? "NONE").not.toBe("JWT");
        expect(route.Properties.AuthorizationType ?? "NONE").not.toBe("CUSTOM");
      } else if (keyRoutes.has(routeKey)) {
        expect(route.Properties.AuthorizationType).toBe("CUSTOM");
      } else {
        expect(route.Properties.AuthorizationType).toBe("JWT");
        expect(routeKey.startsWith("GET /public")).toBe(false);
      }
    }
  });

  test("the key authorizer can touch only APIKEY rows and AdminApiFn gains no key permission", () => {
    const authorizerFn = Object.values(resources("AWS::Lambda::Function")).find((fn) => {
      const variables = (fn.Properties.Environment as { Variables?: Record<string, string> } | undefined)?.Variables;
      return fn.Properties.Handler === "handler.lambda_handler" && variables?.RECORDS_TABLE_NAME !== undefined;
    });
    if (!authorizerFn) {
      throw new Error("key authorizer function is missing");
    }
    const role = authorizerFn.Properties.Role as { "Fn::GetAtt": string[] };
    const authorizer = policyTextForRole(role["Fn::GetAtt"][0]);
    const admin = policyTextForRole(roleIdForHandler("api_handler.lambda_handler"));
    expect(authorizer).toContain("dynamodb:GetItem");
    expect(authorizer).toContain("dynamodb:UpdateItem");
    expect(authorizer).toContain("APIKEY#*");
    expect(authorizer).toContain("dynamodb:LeadingKeys");
    expect(authorizer).toContain("kms:Decrypt");
    expect(authorizer).toContain("kms:GenerateDataKey");
    for (const action of ["dynamodb:Scan", "dynamodb:Query", "dynamodb:PutItem", "dynamodb:DeleteItem"]) {
      expect(authorizer).not.toContain(action);
    }
    expect(admin).not.toContain("APIKEY#*");
    const variables = (authorizerFn.Properties.Environment as { Variables: Record<string, string> }).Variables;
    expect(variables.RECORDS_TABLE_NAME).toBeDefined();
    expect(variables.PUBLIC_API_WRITES_ENABLED).toBeUndefined();
  });

  test("API Gateway invokes AdminApiFn once and the key authorizer once", () => {
    const permissions = Object.values(resources("AWS::Lambda::Permission"));
    const apiGateway = permissions.filter(
      (permission) => permission.Properties.Principal === "apigateway.amazonaws.com",
    );
    expect(apiGateway).toHaveLength(2);
    const names = apiGateway.map((permission) => JSON.stringify(permission.Properties.FunctionName));
    expect(names.filter((name) => name.includes("AdminApiFn"))).toHaveLength(1);
    expect(names.filter((name) => name.includes("PublicApiKeyAuthorizerFn"))).toHaveLength(1);
  });

  test("the API custom domain is regional and created only when both parameters are set", () => {
    const domains = resources("AWS::ApiGatewayV2::DomainName");
    expect(Object.keys(domains)).toHaveLength(1);
    const domain = Object.values(domains)[0];
    expect(domain.Condition).toBe("UseApiCustomDomain");
    const config = (domain.Properties.DomainNameConfigurations as Record<string, string>[])[0];
    expect(config.EndpointType).toBe("REGIONAL");
    expect(config.SecurityPolicy).toBe("TLS_1_2");
    const mappings = resources("AWS::ApiGatewayV2::ApiMapping");
    expect(Object.values(mappings)[0].Condition).toBe("UseApiCustomDomain");
    const outputs = synthesized.toJSON().Outputs as Record<string, { Condition?: string }>;
    expect(outputs.ApiCustomDomainTarget.Condition).toBe("UseApiCustomDomain");
    expect(outputs.ApiCustomDomainUrl.Condition).toBe("UseApiCustomDomain");
  });

  test("the Cognito custom domain coexists with the prefix and CognitoDomain stays on the prefix", () => {
    synthesized.hasParameter("CognitoCustomDomainName", { Type: "String", Default: "" });
    synthesized.hasParameter("CognitoCustomDomainCertificateArn", { Type: "String", Default: "" });
    expect(synthesized.findParameters("CognitoServeCustomDomain")).toEqual({});
    const domains = resources("AWS::Cognito::UserPoolDomain");
    const prefix = Object.values(domains).find(
      (domain) => domain.Properties.CustomDomainConfig === undefined,
    );
    const custom = Object.values(domains).find(
      (domain) => domain.Properties.CustomDomainConfig !== undefined,
    );
    expect(prefix).toBeDefined();
    expect(prefix?.Condition).toBeUndefined();
    expect(custom).toBeDefined();
    expect(custom?.Condition).toMatch(/^AuthUseCustomAuthDomain/);
    const template = synthesized.toJSON() as {
      Resources: Record<string, { Type: string; Properties?: Record<string, unknown> }>;
      Outputs: Record<string, { Condition?: string; Value?: unknown }>;
      Conditions: Record<string, unknown>;
    };
    const deleteDomain = Object.values(template.Resources).find((resource) => {
      if (resource.Type !== "Custom::AWS") {
        return false;
      }
      return JSON.stringify(resource.Properties).includes("deleteUserPoolDomain");
    });
    expect(deleteDomain).toBeUndefined();
    expect(template.Outputs.CognitoCustomDomainTarget.Condition).toBe(custom?.Condition);
    expect(JSON.stringify(template.Outputs.CognitoCustomDomainTarget.Value)).toContain(
      "CloudFrontDistribution",
    );
    const cognitoDomain = JSON.stringify(template.Outputs.CognitoDomain.Value);
    expect(cognitoDomain).not.toContain("Fn::If");
    expect(cognitoDomain).toContain("CognitoDomainPrefix");
    expect(cognitoDomain).toContain(".amazoncognito.com");
    expect(cognitoDomain).not.toContain("CognitoCustomDomainName");
  });

  test("public routes are throttled below the stage default", () => {
    const stage = Object.values(resources("AWS::ApiGatewayV2::Stage"))[0];
    const settings = stage.Properties.RouteSettings as Record<string, { ThrottlingRateLimit: number; ThrottlingBurstLimit: number }>;
    expect(settings["GET /public"]).toEqual({ ThrottlingRateLimit: 2, ThrottlingBurstLimit: 10 });
    expect(settings["GET /public/{proxy+}"]).toEqual({ ThrottlingRateLimit: 2, ThrottlingBurstLimit: 10 });
    expect(settings["PUT /public/{proxy+}"]).toEqual({ ThrottlingRateLimit: 1, ThrottlingBurstLimit: 5 });
    expect(settings["POST /public/{proxy+}"]).toEqual({ ThrottlingRateLimit: 1, ThrottlingBurstLimit: 5 });
  });

  test("the stage and the domain mapping wait for the resources they name", () => {
    const stages = resources("AWS::ApiGatewayV2::Stage");
    const stageId = Object.keys(stages)[0];
    const stageDepends = dependencyList(stages[stageId]);
    for (const routeId of Object.keys(resources("AWS::ApiGatewayV2::Route"))) {
      expect(stageDepends).toContain(routeId);
    }
    const mapping = Object.values(resources("AWS::ApiGatewayV2::ApiMapping"))[0];
    expect(dependencyList(mapping)).toContain(stageId);
  });

  test("the key authorizer has an error alarm", () => {
    const alarms = Object.values(resources("AWS::CloudWatch::Alarm")).map((alarm) => JSON.stringify(alarm.Properties));
    expect(alarms.some((alarm) => alarm.includes("PublicApiKeyAuthorizerFn"))).toBe(true);
  });

  test("EngineFn can invoke itself so a stalled job can start again", () => {
    const engine = policyTextForRole(roleIdForHandler("jobs_handler.lambda_handler"));
    expect(engine).toContain("lambda:InvokeFunction");
    expect(engine).toContain("EngineFn");
  });

  test("the only schedule is EventBridge Scheduler and a failed engine invoke does not retry", () => {
    synthesized.resourceCountIs("AWS::Events::Rule", 0);
    synthesized.resourceCountIs("AWS::Scheduler::Schedule", 4);
    synthesized.hasResourceProperties("AWS::Scheduler::Schedule", {
      Name: "findingalpha-tick",
      ScheduleExpression: "rate(15 minutes)",
      Target: Match.objectLike({
        RetryPolicy: Match.objectLike({ MaximumRetryAttempts: 0 }),
      }),
    });
    synthesized.hasResourceProperties("AWS::Scheduler::Schedule", {
      Name: "findingalpha-ingest-daily",
      ScheduleExpression: "cron(0 12 ? * TUE-SAT *)",
      ScheduleExpressionTimezone: "Asia/Hong_Kong",
    });
    synthesized.hasResourceProperties("AWS::Scheduler::Schedule", {
      Name: "findingalpha-kb-sync-check",
      ScheduleExpression: "cron(30 5 * * ? *)",
      ScheduleExpressionTimezone: "Asia/Hong_Kong",
      Target: Match.objectLike({
        Input: Match.stringLikeRegexp("kb_sync_check"),
        RetryPolicy: Match.objectLike({ MaximumRetryAttempts: 0 }),
      }),
    });
    const schedule = Object.values(resources("AWS::Scheduler::Schedule"))[0];
    expect(JSON.stringify(schedule.Properties.Target)).toContain("tick");
    synthesized.resourceCountIs("AWS::Lambda::EventInvokeConfig", 1);
    synthesized.hasResourceProperties("AWS::Lambda::EventInvokeConfig", {
      MaximumRetryAttempts: 0,
    });
  });

  test("the stage allows one dashboard origin and throttles at 50 per second", () => {
    const api = Object.values(resources("AWS::ApiGatewayV2::Api"))[0];
    const cors = api.Properties.CorsConfiguration as {
      AllowOrigins: unknown[];
      AllowCredentials: boolean;
    };
    expect(cors.AllowOrigins).toHaveLength(1);
    expect(cors.AllowCredentials).toBe(false);
    expect(JSON.stringify(cors.AllowOrigins)).toContain("AdminWebDomainName");
    synthesized.hasResourceProperties("AWS::ApiGatewayV2::Stage", {
      DefaultRouteSettings: Match.objectLike({
        ThrottlingRateLimit: 50,
        ThrottlingBurstLimit: 100,
      }),
    });
  });

  test("the managed knowledge base keeps its index and reads three prefixes", () => {
    const bases = resources("AWS::Bedrock::KnowledgeBase");
    expect(Object.keys(bases)).toHaveLength(1);
    const base = Object.values(bases)[0];
    expect(base.DeletionPolicy).toBe("RetainExceptOnCreate");
    // A replacement keeps the previous knowledge base. The create rollback
    // is what RetainExceptOnCreate covers.
    expect(base.UpdateReplacePolicy).toBe("Retain");
    expect(base.Properties.Name).toBe("findingalpha-theory");
    expect(base.Properties.KnowledgeBaseConfiguration).toEqual({
      Type: "MANAGED",
      ManagedKnowledgeBaseConfiguration: { EmbeddingModelType: "MANAGED" },
    });
    expect(JSON.stringify(base.Properties)).not.toContain("EmbeddingModelArn");
    expect(readTag(base.Properties.Tags, "mcp-multirag-kb")).toBe("true");
    expect(readTag(base.Properties.Tags, "Project")).toBe("Finding Alpha");

    const sources = Object.values(resources("AWS::Bedrock::DataSource"));
    expect(sources).toHaveLength(3);
    const prefixes = sources.map((source) => {
      expect(source.DeletionPolicy).toBeUndefined();
      expect(source.UpdateReplacePolicy).toBeUndefined();
      expect(source.Properties.DataDeletionPolicy).toBe("DELETE");
      const config = source.Properties.DataSourceConfiguration as {
        Type: string;
        ManagedKnowledgeBaseConnectorConfiguration: Record<string, unknown>;
      };
      expect(config.Type).toBe("MANAGED_KNOWLEDGE_BASE_CONNECTOR");
      expect(config.ManagedKnowledgeBaseConnectorConfiguration.SyncSchedule).toBeUndefined();
      expect(config.ManagedKnowledgeBaseConnectorConfiguration.DeletionProtectionConfiguration).toEqual({
        DeletionProtectionStatus: "ENABLED",
        DeletionProtectionThreshold: 15,
      });
      expect(source.Properties.VectorIngestionConfiguration).toBeUndefined();
      const parameters = config.ManagedKnowledgeBaseConnectorConfiguration.ConnectorParameters as {
        filterConfiguration: { inclusionPrefixes: string[]; maxFileSizeInMegaBytes: string };
      };
      expect(parameters.filterConfiguration.maxFileSizeInMegaBytes).toBe("50");
      expect(parameters.filterConfiguration.inclusionPrefixes).toHaveLength(1);
      return parameters.filterConfiguration.inclusionPrefixes[0];
    });
    expect(prefixes.sort()).toEqual(["formula-notes/", "journal/", "theory/"]);
    const dataSources = resources("AWS::Bedrock::DataSource");
    expect(dependencyList(dataSources.FormulaNotesDataSource)).toContain("TheoryDataSource");
    expect(dependencyList(dataSources.JournalDataSource)).toContain("FormulaNotesDataSource");

    const role = Object.values(resources("AWS::IAM::Role")).find((candidate) =>
      JSON.stringify(candidate.Properties.AssumeRolePolicyDocument).includes("knowledge-base/*"),
    );
    if (!role) {
      throw new Error("knowledge base role is missing");
    }
    const policy = JSON.stringify(role.Properties.Policies);
    expect(policy).toContain("s3:ListBucket");
    expect(policy).toContain("s3:GetObject");
    expect(policy).toContain("theory/*");
    expect(policy).toContain("formula-notes/*");
    expect(policy).toContain("journal/*");
    expect(policy).not.toContain("s3:prefix");
    expect(policy).not.toContain("scans/");
    expect(policy).not.toContain("bedrock:InvokeModel");
    expect(policy).toContain("cloudwatch:PutMetricData");
    expect(policy).toContain("AWS/Bedrock/KnowledgeBases");

    const admin = policyTextForRole(roleIdForHandler("api_handler.lambda_handler"));
    const engine = policyTextForRole(roleIdForHandler("jobs_handler.lambda_handler"));
    expect(admin).not.toContain("bedrock:");
    for (const action of [
      "bedrock:Retrieve",
      "bedrock:StartIngestionJob",
      "bedrock:GetIngestionJob",
      "bedrock:ListIngestionJobs",
      "bedrock:ListKnowledgeBaseDocuments",
      "bedrock:StopIngestionJob",
    ]) {
      expect(engine).toContain(action);
    }
    const engineFn = Object.values(resources("AWS::Lambda::Function")).find(
      (fn) => fn.Properties.Handler === "jobs_handler.lambda_handler",
    );
    const variables = (engineFn?.Properties.Environment as { Variables: Record<string, unknown> }).Variables;
    expect(variables.KNOWLEDGE_BASE_ID).toBeDefined();
    expect(JSON.stringify(variables.KB_DATA_SOURCE_IDS)).toContain("theory/");
    expect(JSON.stringify(variables.KB_DATA_SOURCE_IDS)).toContain("formula-notes/");
    expect(JSON.stringify(variables.KB_DATA_SOURCE_IDS)).toContain("journal/");

    synthesized.hasResourceProperties("AWS::CloudWatch::Alarm", {
      MetricName: "RawDataSize",
      Namespace: "AWS/Bedrock/KnowledgeBases",
      Threshold: 2,
      ComparisonOperator: "GreaterThanThreshold",
      TreatMissingData: "ignore",
    });
    const alarm = Object.values(resources("AWS::CloudWatch::Alarm")).find(
      (candidate) => candidate.Properties.MetricName === "RawDataSize",
    );
    expect(JSON.stringify(alarm?.Properties.Dimensions)).toContain("knowledge-base/");
    expect(alarm?.Properties.AlarmActions).toBeUndefined();

    const outputs = synthesized.toJSON().Outputs as Record<string, { Value: unknown }>;
    expect(outputs.KnowledgeBaseId.Value).toBeDefined();
    expect(outputs.KbBucketName.Value).toBeDefined();
  });
});
