import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cwd } from "node:process";
import { describe, expect, it } from "vitest";

const root = cwd();
const config = JSON.parse(readFileSync(resolve(root, ".lighthouserc.json"), "utf8")) as {
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

describe("lighthouse shell", () => {
  it("paints the logo in the document, before React", () => {
    const html = readFileSync(resolve(root, "index.html"), "utf8");
    const body = html.slice(html.indexOf("<body"));
    const rootMarkup = body.slice(body.indexOf('<div id="root">'), body.indexOf("</div>"));
    expect(rootMarkup).toContain('src="/logo.png"');
    expect(rootMarkup).toContain('alt="Finding Alpha"');
    expect(rootMarkup).toContain('fetchpriority="high"');
  });

  it("keeps the logo visible while the entrance animation runs", () => {
    const css = readFileSync(resolve(root, "src/index.css"), "utf8");
    const frames = css.slice(css.indexOf("@keyframes logo-in"), css.indexOf("prefers-reduced-motion"));
    expect(frames).not.toContain("opacity");
  });
});
