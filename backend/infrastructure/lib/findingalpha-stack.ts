import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import { AuthConstruct } from "./constructs/auth";
import { defineAlarms } from "./alarms";
import { defineBuckets, defineSharedEncryption, defineTables } from "./data";
import { defineFunctions, grantEngineSecrets } from "./functions";
import { defineKnowledgeBase } from "./knowledge-base";
import { defineHttpApi } from "./http-api";
import { defineOutputs } from "./outputs";
import { defineParameters } from "./parameters";
import { defineSchedules } from "./schedules";
import { defineSecrets } from "./secrets";
import { tagStack } from "./tags";

export class FindingalphaStack extends cdk.Stack {
  /** Execute-api URL. The deployed admin web still imports this export. */
  public readonly executeApiEndpoint: string;
  /** Effective Cognito OAuth origin; same value as the CognitoDomain output. */
  public readonly cognitoOAuthBaseUrl: string;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);
    tagStack(this);
    // Empty hostname and certificate parameters fail the length and ARN
    // checks. Both custom domains are created only when their parameters
    // are set. An acknowledgement on the stack covers those warnings,
    // including ones that carry no resource context.
    cdk.Validations.of(this).acknowledge({
      id: "CloudFormation-Validate::W1030",
      reason:
        "Optional Cognito and API custom domains. Empty defaults fail the length and ARN checks, and each domain is created only when both of its parameters are set.",
    });
    const parameters = defineParameters(this);
    const { sharedEncryptionKey, lambdaDeadLetterQueue } = defineSharedEncryption(this);
    const auth = new AuthConstruct(this, "Auth", {
      adminWebDomainParameter: parameters.adminWebDomainName,
      googleClientIdParameter: parameters.googleClientId,
      googleClientSecretParameter: parameters.googleClientSecret,
      cognitoDomainPrefixParameter: parameters.cognitoDomainPrefix,
      cognitoCustomDomainNameParameter: parameters.cognitoCustomDomainName,
      cognitoCustomDomainCertificateArnParameter: parameters.cognitoCustomDomainCertificateArn,
      adminFederatedEmailAllowlistParameter: parameters.adminFederatedEmailAllowlist,
      sharedEncryptionKey,
      sharedDeadLetterQueue: lambdaDeadLetterQueue,
    });
    this.cognitoOAuthBaseUrl = auth.cognitoOAuthBaseUrl;
    const { recordsTable, auditLogTable } = defineTables(this, sharedEncryptionKey);
    const { dataBucket, kbBucket } = defineBuckets(this);
    const secrets = defineSecrets(this, sharedEncryptionKey);
    const { adminFn, engineFn } = defineFunctions(this, {
      parameters,
      sharedEncryptionKey,
      lambdaDeadLetterQueue,
      recordsTable,
      auditLogTable,
      dataBucket,
      kbBucket,
    });
    grantEngineSecrets(engineFn, secrets);
    defineKnowledgeBase(this, { kbBucket, engineFn });
    const { httpApi, keyAuthorizerFn, adminApiBaseUrl } = defineHttpApi(this, {
      adminFn,
      userPoolId: auth.userPool.userPoolId,
      userPoolClientId: auth.userPoolClient.userPoolClientId,
      adminWebDomainName: parameters.adminWebDomainName,
      sharedEncryptionKey,
      recordsTable,
      lambdaDeadLetterQueue,
      apiCustomDomainName: parameters.apiCustomDomainName,
      apiCustomDomainCertificateArn: parameters.apiCustomDomainCertificateArn,
    });
    this.executeApiEndpoint = httpApi.apiEndpoint;
    defineSchedules(this, engineFn);
    defineAlarms(this, [adminFn, engineFn, auth.preTokenFn, keyAuthorizerFn], lambdaDeadLetterQueue);
    defineOutputs(this, {
      userPoolId: auth.userPool.userPoolId,
      userPoolClientId: auth.userPoolClient.userPoolClientId,
      cognitoDomain: auth.cognitoOAuthBaseUrl,
      adminApiBaseUrl,
      recordsTableName: recordsTable.tableName,
      dataBucketName: dataBucket.bucketName,
      kbBucketName: kbBucket.bucketName,
      engineFunctionName: engineFn.functionName,
    });
    // Same pattern as ApiCustomDomainTarget: only when both custom-domain
    // parameters are set. The auth DNS CNAME points at this CloudFront host.
    new cdk.CfnOutput(this, "CognitoCustomDomainTarget", {
      value: auth.cognitoCustomHostedDomain.attrCloudFrontDistribution,
      condition: auth.useCustomAuthDomain,
      description:
        "CloudFront hostname for the Cognito custom Hosted UI. The auth DNS record points here.",
    });
  }
}
