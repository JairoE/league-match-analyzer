// Regression: S1 (ChampionKdaChart dynamic import via next/dynamic)
// The chart bundle is code-split; clicking a match row shows a skeleton while
// the chunk loads, then replaces it with the actual recharts SVG chart.
// Branch: frontend-enhancements
// Report: .gstack/qa-reports/

import {test, expect} from "@playwright/test";
import {mockRiotAccountRoutes, riotAccountUrl} from "./helpers";

test.describe("MatchCard — ChampionKdaChart dynamic import (S1)", () => {
  test.beforeEach(async ({page}) => {
    await mockRiotAccountRoutes(page);
  });

  test("Expanding a match row opens the detail panel", async ({page}) => {
    await page.goto(riotAccountUrl());
    await expect(page.getByRole("cell", {name: "Ranked Solo"}).first()).toBeVisible({
      timeout: 10_000,
    });

    // Click the first match row (Ranked Solo — Yasuo)
    await page.locator("tbody tr").first().click();

    // Close button from MatchDetailPanel confirms the panel is open
    await expect(
      page.getByRole("button", {name: "Close match detail"})
    ).toBeVisible({timeout: 5_000});
  });

  test("Expanding a Yasuo row with 2 history points loads the KDA chart", async ({page}) => {
    await page.goto(riotAccountUrl());
    await expect(page.getByRole("cell", {name: "Ranked Solo"}).first()).toBeVisible({
      timeout: 10_000,
    });

    // Fixture has RANKED_MATCH_1 and RANKED_MATCH_2 both on Yasuo.
    // Expanding either shows a 2-point KDA history → chart should render.
    await page.locator("tbody tr").first().click();
    await expect(
      page.getByRole("button", {name: "Close match detail"})
    ).toBeVisible({timeout: 5_000});

    // The chart label appears once the dynamic chunk finishes loading
    await expect(page.getByText("Champion KDA History")).toBeVisible({
      timeout: 10_000,
    });
  });

  test("Chart renders as an SVG (recharts output)", async ({page}) => {
    await page.goto(riotAccountUrl());
    await expect(page.getByRole("cell", {name: "Ranked Solo"}).first()).toBeVisible({
      timeout: 10_000,
    });

    await page.locator("tbody tr").first().click();
    await expect(page.getByText("Champion KDA History")).toBeVisible({
      timeout: 10_000,
    });

    // Recharts renders an SVG element inside the chart container
    const chartSvg = page
      .locator(".recharts-wrapper svg, .recharts-surface")
      .first();
    await expect(chartSvg).toBeVisible({timeout: 5_000});
  });

  test("Closing and re-expanding a row re-shows the chart", async ({page}) => {
    await page.goto(riotAccountUrl());
    await expect(page.getByRole("cell", {name: "Ranked Solo"}).first()).toBeVisible({
      timeout: 10_000,
    });

    // Expand
    await page.locator("tbody tr").first().click();
    await expect(page.getByText("Champion KDA History")).toBeVisible({
      timeout: 10_000,
    });

    // Close via the close button
    await page.getByRole("button", {name: "Close match detail"}).click();
    await expect(page.getByText("Champion KDA History")).toHaveCount(0);

    // Re-expand — DynamicImportBoundary resetKey must reset any error state
    await page.locator("tbody tr").first().click();
    await expect(page.getByText("Champion KDA History")).toBeVisible({
      timeout: 10_000,
    });
  });

  test("Expanding a match on a unique champion (no 2-game history) shows no chart", async ({page}) => {
    await page.goto(riotAccountUrl());
    await expect(page.getByRole("cell", {name: "Ranked Solo"}).first()).toBeVisible({
      timeout: 10_000,
    });

    // ARAM_MATCH is 4th row — the Lux match (only 1 Lux game, no chart)
    const aramRow = page
      .locator("tbody tr")
      .filter({hasText: "ARAM"})
      .first();
    await aramRow.click();

    await expect(
      page.getByRole("button", {name: "Close match detail"})
    ).toBeVisible({timeout: 5_000});

    // No "Champion KDA History" — single-game champions don't get a chart
    // Give it a brief moment in case of late dynamic import
    await page.waitForTimeout(1_000);
    await expect(page.getByText("Champion KDA History")).toHaveCount(0);
  });

  test("No JS errors when expanding and collapsing match rows", async ({page}) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));

    await page.goto(riotAccountUrl());
    await expect(page.getByRole("cell", {name: "Ranked Solo"}).first()).toBeVisible({
      timeout: 10_000,
    });

    await page.locator("tbody tr").first().click();
    await expect(page.getByText("Champion KDA History")).toBeVisible({
      timeout: 10_000,
    });
    await page.getByRole("button", {name: "Close match detail"}).click();

    const realErrors = errors.filter(
      (e) => !e.includes("Warning:") && !e.includes("hydrat")
    );
    expect(realErrors).toHaveLength(0);
  });
});
