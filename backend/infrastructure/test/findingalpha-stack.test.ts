import * as cdk from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import { FindingalphaStack } from "../lib/findingalpha-stack";

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

beforeAll(() => {
  const app = new cdk.App({ context: { "aws:cdk:bundling-stacks": [] } });
  const stack = new FindingalphaStack(app, "findingalpha", { env: ENV });
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
    synthesized.resourceCountIs("AWS::Scheduler::Schedule", 1);
    synthesized.hasResourceProperties("AWS::Scheduler::Schedule", {
      Name: "findingalpha-tick",
      ScheduleExpression: "rate(15 minutes)",
      Target: Match.objectLike({
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
});
