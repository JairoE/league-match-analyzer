// Regression: S2 (useTransition tab switching) + S5 (matchDetails reference stability)
// Branch: frontend-enhancements

import {test, expect} from "@playwright/test";
import {gotoAccountAndWait, mockRiotAccountRoutes} from "./helpers";

// MatchRow renders <tr role="button">, which overrides the implicit row role.
// We count visible match rows via the first cell (queue-mode label) instead.
function queueLabelCells(page: import("@playwright/test").Page) {
  return page
    .getByRole("cell")
    .filter({hasText: /^(Ranked Solo|Normal Draft|ARAM)$/});
}

test.describe("MatchesTable — queue group tabs", () => {
  test.beforeEach(async ({page}) => {
    await mockRiotAccountRoutes(page);
  });

  test("All tab shows all 4 fixture matches", async ({page}) => {
    await gotoAccountAndWait(page);

    // "All" tab is present and initially active
    await expect(
      page.getByTestId("tab-bar").getByRole("button", {name: "All", exact: true})
    ).toBeVisible();

    // Fixture has 4 matches: 2 ranked solo + 1 normal + 1 ARAM
    await expect(queueLabelCells(page)).toHaveCount(4);
  });

  test("Ranked Solo tab filters to only ranked matches", async ({page}) => {
    await gotoAccountAndWait(page);

    await page
      .getByTestId("tab-bar")
      .getByRole("button", {name: "Ranked Solo", exact: true})
      .click();

    await expect(page.getByRole("cell", {name: "Ranked Solo"})).toHaveCount(2);
    await expect(page.getByRole("cell", {name: "Normal Draft"})).toHaveCount(0);
    await expect(page.getByRole("cell", {name: "ARAM"})).toHaveCount(0);
  });

  test("Normal tab filters to only normal-SR matches", async ({page}) => {
    await gotoAccountAndWait(page);

    await page
      .getByTestId("tab-bar")
      .getByRole("button", {name: "Normal", exact: true})
      .click();

    await expect(page.getByRole("cell", {name: "Normal Draft"})).toHaveCount(1);
    await expect(page.getByRole("cell", {name: "Ranked Solo"})).toHaveCount(0);
  });

  test("ARAM tab filters to only ARAM matches", async ({page}) => {
    await gotoAccountAndWait(page);

    await page
      .getByTestId("tab-bar")
      .getByRole("button", {name: "ARAM", exact: true})
      .click();

    await expect(page.getByRole("cell", {name: "ARAM"})).toHaveCount(1);
    await expect(page.getByRole("cell", {name: "Ranked Solo"})).toHaveCount(0);
  });
});

// S5: matchDetails reference stability — summary bar shows correct W/L counts.
// The matchSummaryStats useMemo must not re-run unconditionally on every poll
// tick. Verifying the numbers are correct (not stale/zeroed) confirms the
// memo did not return empty on some renders due to unstable refs.
test.describe("MatchesTable — summary stats bar (S5 matchDetails stability)", () => {
  test.beforeEach(async ({page}) => {
    await mockRiotAccountRoutes(page);
  });

  test("Summary bar shows correct W/L for All tab (3W 1L)", async ({page}) => {
    await gotoAccountAndWait(page);

    // All fixture matches: RANKED_MATCH_1(W) + RANKED_MATCH_2(L) + NORMAL_MATCH(W) + ARAM_MATCH(W) = 3W 1L
    await expect(page.getByText("3W")).toBeVisible();
    await expect(page.getByText("1L")).toBeVisible();
  });

  test("Summary bar updates when tab filters change the match set", async ({page}) => {
    await gotoAccountAndWait(page);

    const tabBar = page.getByTestId("tab-bar");

    await tabBar.getByRole("button", {name: "Ranked Solo", exact: true}).click();
    // Ranked: RANKED_MATCH_1(W) + RANKED_MATCH_2(L) = 1W 1L
    await expect(page.getByText("1W")).toBeVisible();
    await expect(page.getByText("1L")).toBeVisible();

    await tabBar.getByRole("button", {name: "ARAM", exact: true}).click();
    // ARAM: only ARAM_MATCH (win)
    await expect(page.getByText("1W")).toBeVisible();
    await expect(page.getByText("0L")).toBeVisible();
  });
});
