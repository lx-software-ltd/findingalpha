import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import { AuthConstruct } from "./constructs/auth";
import { defineAlarms } from "./alarms";
import { defineBuckets, defineSharedEncryption, defineTables } from "./data";
import { defineFunctions, grantEngineSecrets } from "./functions";
import { defineHttpApi } from "./http-api";
import { defineOutputs } from "./outputs";
import { defineParameters } from "./parameters";
import { defineSchedules } from "./schedules";
import { defineSecrets } from "./secrets";

export class FindingalphaStack extends cdk.Stack {
  public readonly httpApiEndpoint: string;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);
    // CDK reports this on the stack, and an acknowledgement here also covers
    // the conditional domain resource. The empty defaults are unused.
    cdk.Validations.of(this).acknowledge({
      id: "CloudFormation-Validate::W1030",
      reason:
        "Optional Cognito custom domain. Empty defaults fail the length and ARN checks, and the resource is created only when both parameters are set.",
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
    const { httpApi } = defineHttpApi(this, {
      adminFn,
      userPoolId: auth.userPool.userPoolId,
      userPoolClientId: auth.userPoolClient.userPoolClientId,
      adminWebDomainName: parameters.adminWebDomainName,
      sharedEncryptionKey,
    });
    this.httpApiEndpoint = httpApi.apiEndpoint;
    defineSchedules(this, engineFn);
    defineAlarms(this, [adminFn, engineFn, auth.preTokenFn], lambdaDeadLetterQueue);
    defineOutputs(this, {
      userPoolId: auth.userPool.userPoolId,
      userPoolClientId: auth.userPoolClient.userPoolClientId,
      cognitoDomain: auth.cognitoOAuthBaseUrl,
      adminApiBaseUrl: httpApi.apiEndpoint,
      recordsTableName: recordsTable.tableName,
      dataBucketName: dataBucket.bucketName,
      kbBucketName: kbBucket.bucketName,
      engineFunctionName: engineFn.functionName,
    });
  }
}
