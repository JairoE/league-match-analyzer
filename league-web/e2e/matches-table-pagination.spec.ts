// Regression: S2 (useTransition for pagination page changes)
// Branch: frontend-enhancements

import {test, expect} from "@playwright/test";
import {gotoAccountAndWait, mockRiotAccountRoutes} from "./helpers";

test.describe("MatchesTable — pagination (S2 useTransition)", () => {
  test.beforeEach(async ({page}) => {
    await mockRiotAccountRoutes(page, {page2: true});
  });

  test("Pagination controls appear when total > page size", async ({page}) => {
    await gotoAccountAndWait(page);

    // Fixture: total=40, last_page=2, so pagination renders
    await expect(page.getByText("40 matches total")).toBeVisible();
    await expect(page.getByText("Page 1 of 2")).toBeVisible();

    // Previous is disabled on page 1; Next is enabled
    await expect(page.getByRole("button", {name: "Previous", exact: true})).toBeDisabled();
    await expect(page.getByRole("button", {name: "Next", exact: true})).toBeEnabled();
  });

  test("Clicking Next navigates to page 2 without JS errors", async ({page}) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));

    await gotoAccountAndWait(page);

    await page.getByRole("button", {name: "Next", exact: true}).click();

    await expect(page.getByText("Page 2 of 2")).toBeVisible({timeout: 10_000});
    await expect(page.getByRole("button", {name: "Next", exact: true})).toBeDisabled();
    await expect(page.getByRole("button", {name: "Previous", exact: true})).toBeEnabled();

    const realErrors = errors.filter(
      (e) =>
        !e.includes("Hydration") &&
        !e.includes("hydrat") &&
        !e.includes("Warning:")
    );
    expect(realErrors).toHaveLength(0);
  });

  test("Clicking Previous navigates back to page 1", async ({page}) => {
    await gotoAccountAndWait(page);

    await page.getByRole("button", {name: "Next", exact: true}).click();
    await expect(page.getByText("Page 2 of 2")).toBeVisible({timeout: 10_000});

    await page.getByRole("button", {name: "Previous", exact: true}).click();
    await expect(page.getByText("Page 1 of 2")).toBeVisible({timeout: 10_000});

    await expect(page.getByRole("button", {name: "Previous", exact: true})).toBeDisabled();
  });
});
