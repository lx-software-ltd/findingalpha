import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cwd } from "node:process";
import { describe, expect, it } from "vitest";

const config = JSON.parse(readFileSync(resolve(cwd(), ".lighthouserc.json"), "utf8")) as {
  ci: {
    collect: { staticDistDir: string; url: string[]; numberOfRuns: number };
    assert: { aggregationMethod: string; assertions: Record<string, unknown> };
    upload: { target: string };
  };
};

describe("lighthouse config", () => {
  it("audits the logo page from the Vite build", () => {
    expect(config.ci.collect.staticDistDir).toBe("./dist");
    expect(config.ci.collect.url).toEqual(["http://localhost:9000/"]);
    expect(config.ci.collect.numberOfRuns).toBe(3);
    expect(config.ci.collect).not.toHaveProperty("isSinglePageApplication");
    expect(config.ci.assert.aggregationMethod).toBe("median");
    expect(config.ci.upload.target).toBe("temporary-public-storage");
  });

  it("requires the four category scores the other public sites use", () => {
    const assertions = config.ci.assert.assertions;
    for (const category of ["performance", "accessibility", "best-practices", "seo"]) {
      expect(assertions[`categories:${category}`]).toEqual(["error", { minScore: 0.9 }]);
    }
    expect(assertions["offscreen-images"]).toBeUndefined();
  });
});
