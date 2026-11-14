import * as cdk from "aws-cdk-lib";
import * as apigwv2 from "aws-cdk-lib/aws-apigatewayv2";
import { HttpJwtAuthorizer } from "aws-cdk-lib/aws-apigatewayv2-authorizers";
import { HttpLambdaIntegration } from "aws-cdk-lib/aws-apigatewayv2-integrations";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import type * as kms from "aws-cdk-lib/aws-kms";
import type * as lambda from "aws-cdk-lib/aws-lambda";
import { ROUTES } from "./api-routes";

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
  },
) {
  const issuer = `https://cognito-idp.${cdk.Stack.of(scope).region}.amazonaws.com/${input.userPoolId}`;
  const jwtAuthorizer = new HttpJwtAuthorizer("cognito-jwt", issuer, {
    jwtAudience: [input.userPoolClientId],
  });
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
  for (const route of ROUTES) {
    httpApi.addRoutes({
      path: route.path,
      methods: [...route.methods],
      integration,
      ...(route.auth === "jwt" ? { authorizer: jwtAuthorizer } : {}),
    });
  }
  return { httpApi, jwtAuthorizer };
}
