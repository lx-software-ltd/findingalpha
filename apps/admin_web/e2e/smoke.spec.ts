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

test("methodology lists provisional factors", async ({ page }, testInfo) => {
  await page.goto("/methodology");
  await expect(page.getByRole("heading", { name: "Methodology" })).toBeVisible();
  await expect(page.getByText("Status provisional").first()).toBeVisible();
  await expect(page.getByText(/Register hash abc123abc123abcd/)).toBeVisible();
  if (testInfo.project.name === "phone") {
    await expect(
      page.locator("td[data-column='name'] .admin-table-cell-meta").filter({ hasText: "NOPAT_ttm / average(investedCapital)" }),
    ).toBeVisible();
    await page.getByRole("row", { name: /Return on invested capital/ }).click();
    await expect(page.locator(".admin-expand.is-open")).toContainText("maxTaxRate 0.35");
  }
  expect(await overflows(page)).toBe(false);
});

test("screen shows the shortlist and the equity curves", async ({ page }, testInfo) => {
  await page.goto("/screen");
  await expect(page.getByRole("heading", { name: "Screen" })).toBeVisible();
  const aaa = page.getByRole("row", { name: /AAA/ });
  await expect(aaa).toBeVisible();
  if (testInfo.project.name === "phone") {
    const sort = page.getByLabel("Sort", { exact: true });
    await expect(sort).toBeVisible();
    await expect(page.locator("td[data-column='symbol'] .admin-table-cell-meta").first()).toContainText("Rank 1");
    await sort.selectOption("symbol:desc");
    await expect.poll(async () => {
      const bbb = await page.getByRole("row", { name: /BBB/ }).boundingBox();
      const top = await aaa.boundingBox();
      return bbb !== null && top !== null && bbb.y < top.y;
    }).toBe(true);
    await aaa.click();
    await expect(page.locator(".admin-expand.is-open")).toContainText("Quality: 0.40");
    await expect(page.locator(".admin-expand.is-open")).toContainText("Sector: tech");
  }
  if (testInfo.project.name === "desktop") {
    await expect(page.getByLabel("Sort", { exact: true })).toBeHidden();
    const date = await page.getByLabel("Date").boundingBox();
    expect(date?.width ?? 999).toBeLessThan(220);
    await page.getByRole("button", { name: "Sort by Symbol" }).click();
    await page.getByRole("button", { name: /Sorted by Symbol, ascending/ }).click();
    await expect.poll(async () => {
      const bbb = await page.getByRole("row", { name: /BBB/ }).boundingBox();
      const top = await aaa.boundingBox();
      return bbb !== null && top !== null && bbb.y < top.y;
    }).toBe(true);
  }
  await page.getByRole("tab", { name: "Backtest" }).click();
  await expect(page.getByRole("img", { name: "Backtest equity curves" })).toBeVisible();
  await expect(page.getByText("Hit rate")).toBeVisible();
  if (testInfo.project.name === "phone") {
    const meta = page.locator("td[data-column='period'] .admin-table-cell-meta").first();
    await expect(meta).toBeVisible();
    await expect(meta).toContainText("CAGR");
  }
  expect(await overflows(page)).toBe(false);
});

test("system shows the three tables", async ({ page }, testInfo) => {
  await page.goto("/system");
  await expect(page.getByRole("heading", { name: "Switches" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Jobs" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent runs" })).toBeVisible();
  await expect(page.getByText("Broker mode")).toBeVisible();
  if (testInfo.project.name === "phone") {
    const switchName = await page.locator("td[data-column='name']").first().boundingBox();
    expect(switchName?.width ?? 0).toBeGreaterThan(180);
    const jobName = await page.locator("td[data-column='job']").first().boundingBox();
    expect(jobName?.width ?? 0).toBeGreaterThan(140);
    const rotation = page.locator("tr", { hasText: "rotation" });
    await expect(rotation.locator(".admin-table-cell-meta").first()).toContainText("expires");
    await expect(rotation.locator(".admin-table-cell-meta").nth(1)).toContainText("operate");
    await expect(page.locator("tr", { hasText: "ingest_daily" }).locator(".admin-table-cell-meta").last()).toContainText("timeout");
  }
  expect(await overflows(page)).toBe(false);
});
