import * as cdk from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import { wireFindingalphaApp } from "../lib/app-assembly";

const ENV = { account: "123456789012", region: "ap-southeast-1" };
const EXECUTE_API_EXPORT = "findingalpha:ExportsOutputFnGetAttHttpApiF5A9A8A7ApiEndpoint082134F8";

type Output = { Value?: unknown; Export?: { Name?: string } };

function ifConditionNames(value: unknown): string[] {
  const names: string[] = [];
  const walk = (node: unknown): void => {
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (!node || typeof node !== "object") {
      return;
    }
    const record = node as Record<string, unknown>;
    const branch = record["Fn::If"];
    if (Array.isArray(branch) && typeof branch[0] === "string") {
      names.push(branch[0]);
    }
    for (const child of Object.values(record)) {
      walk(child);
    }
  };
  walk(value);
  return names;
}

function isRawParameterExport(output: Output, parameterName: string): boolean {
  if (!output.Export) {
    return false;
  }
  const value = output.Value;
  if (!value || typeof value !== "object") {
    return false;
  }
  const ref = value as { Ref?: string };
  return ref.Ref === parameterName && Object.keys(value).length === 1;
}

describe("synthesized templates", () => {
  const app = new cdk.App({ context: { "aws:cdk:bundling-stacks": [] } });
  const { backend, adminWeb } = wireFindingalphaApp(app, ENV);

  test("every Fn::If names a condition in that template", () => {
    for (const child of app.node.children) {
      if (!cdk.Stack.isStack(child)) {
        continue;
      }
      const template = Template.fromStack(child).toJSON() as { Conditions?: Record<string, unknown> };
      const defined = new Set(Object.keys(template.Conditions ?? {}));
      const missing = ifConditionNames(template).filter((name) => !defined.has(name));
      expect(missing).toEqual([]);
    }
  });

  test("the admin web imports the resolved API URL and keeps the execute-api export", () => {
    const backendTemplate = Template.fromStack(backend).toJSON() as { Outputs?: Record<string, Output> };
    const exports = Object.values(backendTemplate.Outputs ?? {});
    expect(exports.some((output) => isRawParameterExport(output, "ApiCustomDomainName"))).toBe(false);
    expect(exports.some((output) => output.Export?.Name === EXECUTE_API_EXPORT)).toBe(true);
    const adminText = JSON.stringify(Template.fromStack(adminWeb).toJSON());
    expect(adminText).toContain("findingalpha-AdminApiBaseUrl");
    expect(adminText).not.toContain("UseApiCustomDomain");
    expect(adminWeb.dependencies).toContain(backend);
  });
});
