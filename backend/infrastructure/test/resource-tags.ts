import type { App, Stack } from "aws-cdk-lib";
import { ORGANIZATION, PROJECT } from "../lib/tags";

type TemplateResource = {
  Type: string;
  Properties?: { Tags?: unknown; UserPoolTags?: unknown };
};

export function readTag(tags: unknown, key: string): string | undefined {
  if (Array.isArray(tags)) {
    const found = tags.find(
      (tag) => tag && typeof tag === "object" && (tag as { Key?: string }).Key === key,
    ) as { Value?: string } | undefined;
    return typeof found?.Value === "string" ? found.Value : undefined;
  }
  if (tags && typeof tags === "object") {
    const value = (tags as Record<string, unknown>)[key];
    return typeof value === "string" ? value : undefined;
  }
  return undefined;
}

export function tagReport(app: App, stack: Stack): { missing: string[]; untaggedTypes: string[] } {
  const artifact = app.synth().getStackArtifact(stack.artifactId);
  const missing: string[] = [];
  if (artifact.tags.Organization !== ORGANIZATION || artifact.tags.Project !== PROJECT) {
    missing.push(
      `stack tags ${JSON.stringify({ Organization: artifact.tags.Organization, Project: artifact.tags.Project })}`,
    );
  }
  const resources = artifact.template.Resources as Record<string, TemplateResource>;
  const untagged = new Set<string>();
  for (const [id, resource] of Object.entries(resources)) {
    const tags = resource.Properties?.Tags ?? resource.Properties?.UserPoolTags;
    if (tags === undefined) {
      untagged.add(resource.Type);
      continue;
    }
    if (readTag(tags, "Organization") !== ORGANIZATION || readTag(tags, "Project") !== PROJECT) {
      missing.push(`${resource.Type} ${id} tags=${JSON.stringify(tags)}`);
    }
  }
  return { missing, untaggedTypes: [...untagged].sort() };
}
