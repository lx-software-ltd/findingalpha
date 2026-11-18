import { expect, test, type Page } from "@playwright/test";

async function overflows(page: Page): Promise<boolean> {
  return page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  );
}

test("roadmap renders without horizontal scroll and the nav opens", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Owner tasks" })).toBeVisible();
  expect(await overflows(page)).toBe(false);
  if (testInfo.project.name === "phone") {
    await page.getByRole("button", { name: "Open navigation menu" }).click();
    await expect(page.getByRole("link", { name: "System" })).toBeVisible();
  } else {
    await expect(page.getByRole("link", { name: "System" })).toBeVisible();
  }
});

test("methodology lists provisional factors", async ({ page }) => {
  await page.goto("/methodology");
  await expect(page.getByRole("heading", { name: "Methodology" })).toBeVisible();
  await expect(page.getByText("provisional").first()).toBeVisible();
  expect(await overflows(page)).toBe(false);
});

test("screen shows the shortlist and the equity curves", async ({ page }) => {
  await page.goto("/screen");
  await expect(page.getByRole("heading", { name: "Screen" })).toBeVisible();
  await expect(page.getByRole("button", { name: "AAA" })).toBeVisible();
  await page.getByRole("tab", { name: "Backtest" }).click();
  await expect(page.getByRole("img", { name: "Backtest equity curves" })).toBeVisible();
  expect(await overflows(page)).toBe(false);
});

test("knowledge base shows the sync and a question", async ({ page }) => {
  await page.goto("/knowledge-base");
  await expect(page.getByRole("heading", { name: "Knowledge base" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sync now" })).toBeVisible();
  await expect(page.getByText("q01")).toBeVisible();
  await page.getByRole("button", { name: "Sync now" }).click();
  await expect(page.getByText("Start a knowledge base sync?")).toBeVisible();
  await page.getByRole("button", { name: "Sync", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Sync started.");
  expect(await overflows(page)).toBe(false);
});

test("system shows the three tables", async ({ page }) => {
  await page.goto("/system");
  await expect(page.getByRole("heading", { name: "Switches" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Jobs" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent runs" })).toBeVisible();
  expect(await overflows(page)).toBe(false);
});
