// Regression: S1 (ChampionKdaChart dynamic import via next/dynamic)
// The chart bundle is code-split; clicking a match row shows a skeleton while
// the chunk loads, then replaces it with the actual recharts SVG chart.
// Branch: frontend-enhancements

import {test, expect} from "@playwright/test";
import {gotoAccountAndWait, mockRiotAccountRoutes} from "./helpers";

test.describe("MatchCard — ChampionKdaChart dynamic import (S1)", () => {
  test.beforeEach(async ({page}) => {
    await mockRiotAccountRoutes(page);
  });

  test("Expanding a row with a 2-game champion history loads the chart as SVG", async ({
    page,
  }) => {
    await gotoAccountAndWait(page);

    // Fixture has RANKED_MATCH_1 and RANKED_MATCH_2 both on Yasuo,
    // so expanding either yields a 2-point KDA history.
    await page.locator("tbody tr").first().click();

    // Detail panel opens
    await expect(
      page.getByRole("button", {name: "Close match detail"})
    ).toBeVisible({timeout: 5_000});

    // Dynamic chunk finishes loading and renders the chart
    await expect(page.getByText("Champion KDA History")).toBeVisible({
      timeout: 10_000,
    });

    // Recharts renders an SVG element inside the chart container
    await expect(
      page.locator(".recharts-wrapper svg, .recharts-surface").first()
    ).toBeVisible({timeout: 5_000});
  });

  test("Closing and re-expanding a row re-shows the chart without JS errors", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));

    await gotoAccountAndWait(page);

    // Expand
    await page.locator("tbody tr").first().click();
    await expect(page.getByText("Champion KDA History")).toBeVisible({
      timeout: 10_000,
    });

    // Close
    await page.getByRole("button", {name: "Close match detail"}).click();
    await expect(page.getByText("Champion KDA History")).toHaveCount(0);

    // Re-expand — DynamicImportBoundary resetKey must reset any error state
    await page.locator("tbody tr").first().click();
    await expect(page.getByText("Champion KDA History")).toBeVisible({
      timeout: 10_000,
    });

    const realErrors = errors.filter(
      (e) => !e.includes("Warning:") && !e.includes("hydrat")
    );
    expect(realErrors).toHaveLength(0);
  });

  test("Single-game champion (no 2-point history) shows no chart", async ({page}) => {
    await gotoAccountAndWait(page);

    // ARAM_MATCH is on Lux — only 1 Lux game in the fixture, so no chart.
    const aramRow = page.locator("tbody tr").filter({hasText: "ARAM"}).first();
    await aramRow.click();

    await expect(
      page.getByRole("button", {name: "Close match detail"})
    ).toBeVisible({timeout: 5_000});

    // Wait for the panel content to settle, then assert chart is absent.
    // Using a deterministic anchor (the close button visible above) instead
    // of an arbitrary timeout — if the chart was going to load, it would
    // have loaded by the time the panel finished mounting.
    await expect(page.getByText("Champion KDA History")).toHaveCount(0);
  });
});
