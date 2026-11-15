import * as cdk from "aws-cdk-lib";
import * as apigwv2 from "aws-cdk-lib/aws-apigatewayv2";
import { HttpJwtAuthorizer } from "aws-cdk-lib/aws-apigatewayv2-authorizers";
import { HttpLambdaIntegration } from "aws-cdk-lib/aws-apigatewayv2-integrations";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import type * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import type * as kms from "aws-cdk-lib/aws-kms";
import type * as lambda from "aws-cdk-lib/aws-lambda";
import type * as sqs from "aws-cdk-lib/aws-sqs";
import { ROUTES } from "./api-routes";
import { defineKeyAuthorizer } from "./authorizers";

class SharedPermissionLambdaIntegration extends HttpLambdaIntegration {
  protected completeBind(_options: apigwv2.HttpRouteIntegrationBindOptions): void {
    // Invoke permission is granted once for the whole API.
  }
}

export function defineHttpApi(
  scope: cdk.Stack,
  input: {
    readonly adminFn: lambda.Function;
    readonly userPoolId: string;
    readonly userPoolClientId: string;
    readonly adminWebDomainName: cdk.CfnParameter;
    readonly sharedEncryptionKey: kms.IKey;
    readonly recordsTable: dynamodb.Table;
    readonly lambdaDeadLetterQueue: sqs.Queue;
    readonly apiCustomDomainName: cdk.CfnParameter;
    readonly apiCustomDomainCertificateArn: cdk.CfnParameter;
  },
) {
  const issuer = `https://cognito-idp.${cdk.Stack.of(scope).region}.amazonaws.com/${input.userPoolId}`;
  const jwtAuthorizer = new HttpJwtAuthorizer("cognito-jwt", issuer, {
    jwtAudience: [input.userPoolClientId],
  });
  const keyAuthorizer = defineKeyAuthorizer(scope, input);
  const integration = new SharedPermissionLambdaIntegration("AdminIntegration", input.adminFn);
  const httpApi = new apigwv2.HttpApi(scope, "HttpApi", {
    apiName: "findingalpha-admin-api",
    corsPreflight: {
      allowHeaders: ["authorization", "content-type"],
      allowMethods: [
        apigwv2.CorsHttpMethod.GET,
        apigwv2.CorsHttpMethod.POST,
        apigwv2.CorsHttpMethod.PUT,
        apigwv2.CorsHttpMethod.OPTIONS,
      ],
      allowOrigins: [cdk.Fn.join("", ["https://", input.adminWebDomainName.valueAsString])],
      allowCredentials: false,
    },
  });
  input.adminFn.addPermission("AdminApiInvoke", {
    scope,
    principal: new iam.ServicePrincipal("apigateway.amazonaws.com"),
    sourceArn: httpApi.arnForExecuteApi(),
  });
  const accessLogGroup = new logs.LogGroup(scope, "HttpApiAccessLogs", {
    retention: logs.RetentionDays.ONE_MONTH,
    removalPolicy: cdk.RemovalPolicy.DESTROY,
    encryptionKey: input.sharedEncryptionKey,
  });
  const defaultStage = httpApi.defaultStage?.node.defaultChild as apigwv2.CfnStage;
  defaultStage.accessLogSettings = {
    destinationArn: accessLogGroup.logGroupArn,
    format: JSON.stringify({
      requestId: "$context.requestId",
      routeKey: "$context.routeKey",
      status: "$context.status",
      integrationError: "$context.integrationErrorMessage",
      authorizerError: "$context.authorizer.error",
      httpMethod: "$context.httpMethod",
      path: "$context.path",
      sourceIp: "$context.identity.sourceIp",
      claimSub: "$context.authorizer.claims.sub",
      claimEmail: "$context.authorizer.claims.email",
      claimGroups: "$context.authorizer.claims.cognito:groups",
      claimTokenUse: "$context.authorizer.claims.token_use",
    }),
  };
  accessLogGroup.addToResourcePolicy(
    new iam.PolicyStatement({
      principals: [new iam.ServicePrincipal("apigateway.amazonaws.com")],
      actions: ["logs:CreateLogStream", "logs:PutLogEvents"],
      resources: [`${accessLogGroup.logGroupArn}:*`],
    }),
  );
  defaultStage.defaultRouteSettings = { throttlingRateLimit: 50, throttlingBurstLimit: 100 };
  const routeSettings: Record<string, { ThrottlingRateLimit: number; ThrottlingBurstLimit: number }> = {};
  for (const route of ROUTES) {
    const authorizer = route.auth === "jwt" ? jwtAuthorizer : route.auth === "key" ? keyAuthorizer : undefined;
    httpApi.addRoutes({
      path: route.path,
      methods: [...route.methods],
      integration,
      ...(authorizer ? { authorizer } : {}),
    });
    if (route.throttle) {
      for (const method of route.methods) {
        routeSettings[`${method} ${route.path}`] = {
          ThrottlingRateLimit: route.throttle.rate,
          ThrottlingBurstLimit: route.throttle.burst,
        };
      }
    }
  }
  // The L2 map keeps the inner names in camel case, which CloudFormation ignores.
  defaultStage.addPropertyOverride("RouteSettings", routeSettings);
  defineApiDomain(scope, httpApi, input.apiCustomDomainName, input.apiCustomDomainCertificateArn);
  return { httpApi, jwtAuthorizer };
}

function defineApiDomain(
  scope: cdk.Stack,
  httpApi: apigwv2.HttpApi,
  name: cdk.CfnParameter,
  certificateArn: cdk.CfnParameter,
) {
  const useDomain = new cdk.CfnCondition(scope, "UseApiCustomDomain", {
    expression: cdk.Fn.conditionAnd(
      cdk.Fn.conditionNot(cdk.Fn.conditionEquals(name.valueAsString, "")),
      cdk.Fn.conditionNot(cdk.Fn.conditionEquals(certificateArn.valueAsString, "")),
    ),
  });
  const domain = new apigwv2.CfnDomainName(scope, "ApiCustomDomain", {
    domainName: name.valueAsString,
    domainNameConfigurations: [
      {
        certificateArn: certificateArn.valueAsString,
        endpointType: "REGIONAL",
        securityPolicy: "TLS_1_2",
      },
    ],
  });
  domain.cfnOptions.condition = useDomain;
  const mapping = new apigwv2.CfnApiMapping(scope, "ApiCustomDomainMapping", {
    apiId: httpApi.apiId,
    domainName: domain.ref,
    stage: "$default",
  });
  mapping.cfnOptions.condition = useDomain;
  new cdk.CfnOutput(scope, "ApiCustomDomainTarget", {
    value: domain.attrRegionalDomainName,
    condition: useDomain,
    description: "Regional API Gateway hostname. The api DNS record points here.",
  });
  new cdk.CfnOutput(scope, "ApiCustomDomainUrl", {
    value: cdk.Fn.join("", ["https://", name.valueAsString]),
    condition: useDomain,
  });
}
