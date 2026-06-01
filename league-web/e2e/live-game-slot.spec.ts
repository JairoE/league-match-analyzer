// Regression: S3 (LiveGameSlot / LiveGameCard dynamic import via next/dynamic)
// LiveGameSlot is code-split; the LiveGameCard chunk only loads when a player
// is actually in a live game. The slot renders status-specific UI for all
// other states (idle, connecting, not_in_game, error) without loading the
// card bundle.
// Branch: frontend-enhancements

import {test, expect} from "@playwright/test";
import {
  gotoAccountAndWait,
  mockRiotAccountRoutes,
  riotAccountUrl,
} from "./helpers";

test.describe("LiveGameSlot — dynamic import (S3)", () => {
  test("Page loads without errors when live game returns not_in_game", async ({page}) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));

    await mockRiotAccountRoutes(page);
    await gotoAccountAndWait(page);

    // SSE fixture sends not_in_game → LiveGameSlot renders "No live game."
    await expect(page.getByText("No live game.")).toBeVisible({timeout: 8_000});
    await expect(page.getByRole("button", {name: "Fetch live game"})).toBeVisible();

    const realErrors = errors.filter(
      (e) => !e.includes("Warning:") && !e.includes("hydrat")
    );
    expect(realErrors).toHaveLength(0);
  });

  test("Retry button triggers a new SSE connection", async ({page}) => {
    let sseRequestCount = 0;

    await mockRiotAccountRoutes(page);

    // Override the SSE route to count connections
    await page.route("**/live-game/**/stream", async (route) => {
      sseRequestCount++;
      await route.fulfill({
        status: 200,
        headers: {
          "content-type": "text/event-stream",
          "cache-control": "no-cache",
        },
        body: "event: not_in_game\ndata: {}\n\n",
      });
    });

    await page.goto(riotAccountUrl());
    await expect(page.getByText("No live game.")).toBeVisible({timeout: 8_000});

    const countBefore = sseRequestCount;

    // Click retry and wait for the next SSE request to fire — deterministic
    // signal instead of an arbitrary timeout.
    await Promise.all([
      page.waitForRequest("**/live-game/**/stream"),
      page.getByRole("button", {name: "Fetch live game"}).click(),
    ]);

    expect(sseRequestCount).toBeGreaterThan(countBefore);
  });

  test("Live game SSE error shows retry UI", async ({page}) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));

    // Use the standard mocks, then override only the SSE route to emit error.
    await mockRiotAccountRoutes(page);
    await page.route("**/live-game/**/stream", async (route) => {
      await route.fulfill({
        status: 200,
        headers: {
          "content-type": "text/event-stream",
          "cache-control": "no-cache",
        },
        body: 'event: error\ndata: {"status":503,"error_message":"Service unavailable"}\n\n',
      });
    });

    await gotoAccountAndWait(page);

    // Error state shows retry UI ("Please try again." copy + Fetch live game button)
    await expect(page.getByText("Please try again.")).toBeVisible({timeout: 8_000});
    await expect(page.getByRole("button", {name: "Fetch live game"})).toBeVisible();

    const realErrors = errors.filter(
      (e) => !e.includes("Warning:") && !e.includes("hydrat")
    );
    expect(realErrors).toHaveLength(0);
  });

  test("LiveGameSlot is not rendered when no account is loaded", async ({page}) => {
    // Account 404 with riot_status:404 triggers the deterministic
    // "No search results for the summoner ..." page error, which is what
    // we wait on instead of an arbitrary timeout.
    await page.route("**/search/**/account", async (route) => {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({detail: "riot_api_failed", riot_status: 404}),
      });
    });
    await page.route("**/search/**/matches*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: '{"data":[],"meta":{"page":1,"limit":20,"total":0,"last_page":1}}',
      });
    });
    // Catch any SSE attempt — the test asserts none of the live-game UI shows.
    await page.route("**/live-game/**/stream", async (route) => {
      await route.fulfill({
        status: 200,
        headers: {"content-type": "text/event-stream"},
        body: "",
      });
    });

    await page.goto(riotAccountUrl());

    // Deterministic anchor: the account-error message appears once the
    // account fetch resolves to 404 → targetPuuid stays null →
    // LiveGameSlot returns null.
    await expect(page.getByText(/No search results for the summoner/i)).toBeVisible({
      timeout: 10_000,
    });

    await expect(page.getByText("No live game.")).toHaveCount(0);
    await expect(page.getByText("Checking for live game")).toHaveCount(0);
  });
});
