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

test("system shows the three tables", async ({ page }) => {
  await page.goto("/system");
  await expect(page.getByRole("heading", { name: "Switches" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Jobs" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent runs" })).toBeVisible();
  expect(await overflows(page)).toBe(false);
});
