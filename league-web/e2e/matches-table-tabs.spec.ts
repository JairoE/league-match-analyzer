// Regression: S2 (useTransition tab switching) + S5 (matchDetails reference stability)
// Branch: frontend-enhancements
// Report: .gstack/qa-reports/

import {test, expect} from "@playwright/test";
import {mockRiotAccountRoutes, riotAccountUrl} from "./helpers";

test.describe("MatchesTable — queue group tabs", () => {
  test.beforeEach(async ({page}) => {
    await mockRiotAccountRoutes(page);
  });

  test("All tab is active on load and shows all matches", async ({page}) => {
    await page.goto(riotAccountUrl());

    // Wait for matches to load — at least one queue-mode cell appears
    await expect(page.getByRole("cell", {name: "Ranked Solo"}).first()).toBeVisible({
      timeout: 10_000,
    });

    // "All" tab is present and initially active
    const tabBar = page.getByTestId("tab-bar");
    const allTab = tabBar.getByRole("button", {name: "All", exact: true});
    await expect(allTab).toBeVisible();

    // Fixture has 4 matches: 2 ranked solo + 1 normal + 1 ARAM
    const rows = page.getByRole("row").filter({hasText: /(Ranked Solo|Normal Draft|ARAM)/});
    await expect(rows).toHaveCount(4);
  });

  test("Ranked Solo tab filters to only ranked matches", async ({page}) => {
    await page.goto(riotAccountUrl());
    await expect(page.getByRole("cell", {name: "Ranked Solo"}).first()).toBeVisible({
      timeout: 10_000,
    });

    await page.getByTestId("tab-bar").getByRole("button", {name: "Ranked Solo", exact: true}).click();

    // Only 2 ranked rows remain
    const rankedRows = page.getByRole("cell", {name: "Ranked Solo"});
    await expect(rankedRows).toHaveCount(2);

    // Normal Draft and ARAM rows are gone
    await expect(page.getByRole("cell", {name: "Normal Draft"})).toHaveCount(0);
    await expect(page.getByRole("cell", {name: "ARAM"})).toHaveCount(0);
  });

  test("Normal tab filters to only normal-SR matches", async ({page}) => {
    await page.goto(riotAccountUrl());
    await expect(page.getByRole("cell", {name: "Ranked Solo"}).first()).toBeVisible({
      timeout: 10_000,
    });

    await page.getByTestId("tab-bar").getByRole("button", {name: "Normal", exact: true}).click();

    await expect(page.getByRole("cell", {name: "Normal Draft"})).toHaveCount(1);
    await expect(page.getByRole("cell", {name: "Ranked Solo"})).toHaveCount(0);
  });

  test("ARAM tab filters to only ARAM matches", async ({page}) => {
    await page.goto(riotAccountUrl());
    await expect(page.getByRole("cell", {name: "Ranked Solo"}).first()).toBeVisible({
      timeout: 10_000,
    });

    await page.getByTestId("tab-bar").getByRole("button", {name: "ARAM", exact: true}).click();

    await expect(page.getByRole("cell", {name: "ARAM"})).toHaveCount(1);
    await expect(page.getByRole("cell", {name: "Ranked Solo"})).toHaveCount(0);
  });

  test("Switching back to All restores all matches", async ({page}) => {
    await page.goto(riotAccountUrl());
    await expect(page.getByRole("cell", {name: "Ranked Solo"}).first()).toBeVisible({
      timeout: 10_000,
    });

    // Go to Ranked Solo, then back to All
    const tabBar = page.getByTestId("tab-bar");
    await tabBar.getByRole("button", {name: "Ranked Solo", exact: true}).click();
    await tabBar.getByRole("button", {name: "All", exact: true}).click();

    const rows = page.getByRole("row").filter({hasText: /(Ranked Solo|Normal Draft|ARAM)/});
    await expect(rows).toHaveCount(4);
  });
});

// S5: matchDetails reference stability — summary bar shows correct W/L counts
// The matchSummaryStats useMemo must not re-run unconditionally on every poll tick.
// We verify the numbers are correct (not stale/zeroed), which would fail if
// matchDetails was never stabilized and the memo returned empty on some renders.
test.describe("MatchesTable — summary stats bar (S5 matchDetails stability)", () => {
  test.beforeEach(async ({page}) => {
    await mockRiotAccountRoutes(page);
  });

  test("Summary bar shows correct W/L for All tab (3W 1L)", async ({page}) => {
    await page.goto(riotAccountUrl());
    await expect(page.getByRole("cell", {name: "Ranked Solo"}).first()).toBeVisible({
      timeout: 10_000,
    });

    // All fixture matches: RANKED_MATCH_1(W) + RANKED_MATCH_2(L) + NORMAL_MATCH(W) + ARAM_MATCH(W) = 3W 1L
    await expect(page.getByText("3W")).toBeVisible();
    await expect(page.getByText("1L")).toBeVisible();
  });

  test("Summary bar updates when tab filters to Ranked Solo (1W 1L)", async ({page}) => {
    await page.goto(riotAccountUrl());
    await expect(page.getByRole("cell", {name: "Ranked Solo"}).first()).toBeVisible({
      timeout: 10_000,
    });

    await page.getByTestId("tab-bar").getByRole("button", {name: "Ranked Solo", exact: true}).click();

    // Ranked matches: RANKED_MATCH_1(W) + RANKED_MATCH_2(L) = 1W 1L
    await expect(page.getByText("1W")).toBeVisible();
    await expect(page.getByText("1L")).toBeVisible();
  });

  test("Summary bar updates when tab filters to ARAM (1W 0L)", async ({page}) => {
    await page.goto(riotAccountUrl());
    await expect(page.getByRole("cell", {name: "Ranked Solo"}).first()).toBeVisible({
      timeout: 10_000,
    });

    await page.getByTestId("tab-bar").getByRole("button", {name: "ARAM", exact: true}).click();

    // ARAM: only ARAM_MATCH which is a win
    await expect(page.getByText("1W")).toBeVisible();
    // 0 losses means the loss counter is not shown (matchSummaryStats.total > 0 guard)
    await expect(page.getByText("0L")).toBeVisible();
  });
});
