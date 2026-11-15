import * as cdk from "aws-cdk-lib";
import { cognitoDomainPrefix } from "./shared-contracts";

function text(scope: cdk.Stack, name: string, description: string, extra: Partial<cdk.CfnParameterProps> = {}) {
  return new cdk.CfnParameter(scope, name, { type: "String", description, ...extra });
}

function secret(scope: cdk.Stack, name: string, description: string) {
  return text(scope, name, description, { noEcho: true });
}

function flag(scope: cdk.Stack, name: string, description: string) {
  return text(scope, name, description, {
    allowedValues: ["true", "false"],
    default: "false",
  });
}

/** Parameters for the findingalpha stack. Logical ids are the parameter names. */
export function defineParameters(scope: cdk.Stack) {
  return {
    adminWebDomainName: text(scope, "AdminWebDomainName", "Dashboard hostname, admin.<domain>."),
    googleClientId: text(scope, "GoogleClientId", "Google OAuth client id."),
    googleClientSecret: secret(scope, "GoogleClientSecret", "Google OAuth client secret."),
    adminFederatedEmailAllowlist: text(
      scope,
      "AdminFederatedEmailAllowlist",
      "Comma-separated emails allowed to sign in.",
    ),
    cognitoDomainPrefix: text(scope, "CognitoDomainPrefix", "Hosted UI prefix.", {
      default: cognitoDomainPrefix,
    }),
    cognitoCustomDomainName: text(scope, "CognitoCustomDomainName", "Optional auth.<domain>.", {
      default: "",
    }),
    cognitoCustomDomainCertificateArn: text(
      scope,
      "CognitoCustomDomainCertificateArn",
      "Optional us-east-1 certificate for the custom Hosted UI domain.",
      { default: "" },
    ),
    mailSendingDomain: text(scope, "MailSendingDomain", "Domain SES sends from. Empty disables email.", {
      default: "",
    }),
    briefFromLocalPart: text(scope, "BriefFromLocalPart", "Local part of the sender address.", {
      default: "brief",
    }),
    briefRecipientEmail: text(scope, "BriefRecipientEmail", "Where the daily email goes.", { default: "" }),
    secContactEmail: text(scope, "SecContactEmail", "Contact address in the SEC User-Agent.", { default: "" }),
    ingestEnabled: flag(scope, "IngestEnabled", "Kill switch for data ingest."),
    committeeEnabled: flag(scope, "CommitteeEnabled", "Kill switch for model calls."),
    tradingEnabled: flag(scope, "TradingEnabled", "Kill switch for orders."),
    leverageEnabled: flag(scope, "LeverageEnabled", "Kill switch for leverage above 1."),
    briefEmailEnabled: flag(scope, "BriefEmailEnabled", "Kill switch for the daily email."),
    brokerMode: text(scope, "BrokerMode", "Broker mode. Only paper exists.", {
      allowedValues: ["paper"],
      default: "paper",
    }),
    committeeAnalystModel: text(scope, "CommitteeAnalystModel", "OpenRouter model slug for the analyst.", {
      default: "",
    }),
    committeeChairModel: text(scope, "CommitteeChairModel", "OpenRouter model slug for the chair.", {
      default: "",
    }),
    kbMaxRawBytes: text(scope, "KbMaxRawBytes", "Knowledge base size cap in bytes.", {
      default: "2147483648",
    }),
    kbMaxRetrievalsPerMonth: text(scope, "KbMaxRetrievalsPerMonth", "Retrieval cap per month.", {
      default: "5000",
    }),
    publicApiWritesEnabled: flag(scope, "PublicApiWritesEnabled", "Kill switch for writes by API key."),
    apiCustomDomainName: text(scope, "ApiCustomDomainName", "Optional api.<domain>. Empty skips the hostname.", {
      default: "",
    }),
    apiCustomDomainCertificateArn: text(
      scope,
      "ApiCustomDomainCertificateArn",
      "Certificate in the stack region for api.<domain>.",
      { default: "" },
    ),
  };
}

export type Parameters = ReturnType<typeof defineParameters>;
