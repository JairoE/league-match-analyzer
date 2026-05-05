// Regression: S3 (LiveGameSlot / LiveGameCard dynamic import via next/dynamic)
// LiveGameSlot is code-split; the LiveGameCard chunk only loads when a player
// is actually in a live game. The slot renders status-specific UI for all other
// states (idle, connecting, not_in_game, error) without loading the card bundle.
// Branch: frontend-enhancements
// Report: .gstack/qa-reports/

import {test, expect} from "@playwright/test";
import {mockRiotAccountRoutes, riotAccountUrl} from "./helpers";

test.describe("LiveGameSlot — dynamic import (S3)", () => {
  test("Page loads without errors when live game returns not_in_game", async ({page}) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));

    await mockRiotAccountRoutes(page);
    await page.goto(riotAccountUrl());

    // Matches must load first
    await expect(page.getByRole("cell", {name: "Ranked Solo"}).first()).toBeVisible({
      timeout: 10_000,
    });

    // SSE fixture sends not_in_game → LiveGameSlot renders "No live game."
    await expect(page.getByText("No live game.")).toBeVisible({timeout: 8_000});

    // "Fetch live game" retry button is present
    await expect(page.getByRole("button", {name: "Fetch live game"})).toBeVisible();

    const realErrors = errors.filter(
      (e) => !e.includes("Warning:") && !e.includes("hydrat")
    );
    expect(realErrors).toHaveLength(0);
  });

  test("Retry button is clickable and triggers a new SSE connection", async ({page}) => {
    let sseRequestCount = 0;

    await mockRiotAccountRoutes(page);

    // Override live game route to count requests and always return not_in_game
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

    // Click retry — should trigger a new EventSource connection
    await page.getByRole("button", {name: "Fetch live game"}).click();

    // Brief wait for the new request to fire
    await page.waitForTimeout(500);
    expect(sseRequestCount).toBeGreaterThan(countBefore);
  });

  test("Live game SSE error gracefully shows retry UI", async ({page}) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));

    // Override live game to respond with an error event
    await page.route("**/search/**/account", async (route) => {
      const {ACCOUNT_RESPONSE} = await import("./fixtures/matches");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(ACCOUNT_RESPONSE),
      });
    });
    await page.route("**/search/**/matches*", async (route) => {
      const {PAGE_1_RESPONSE} = await import("./fixtures/matches");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PAGE_1_RESPONSE),
      });
    });
    await page.route("**/riot-accounts/**/rank*", async (route) => {
      await route.fulfill({status: 404, body: "{}"});
    });
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

    await page.goto(riotAccountUrl());
    await expect(page.getByRole("cell", {name: "Ranked Solo"}).first()).toBeVisible({
      timeout: 10_000,
    });

    // Error state shows retry UI — either "Please try again." or similar
    await expect(
      page.getByRole("button", {name: "Fetch live game"})
    ).toBeVisible({timeout: 8_000});

    const realErrors = errors.filter(
      (e) => !e.includes("Warning:") && !e.includes("hydrat")
    );
    expect(realErrors).toHaveLength(0);
  });

  test("LiveGameSlot is not rendered when targetPuuid is null (no account loaded)", async ({page}) => {
    // Route account to 404 so account never loads → targetPuuid stays null
    await page.route("**/search/**/account", async (route) => {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({detail: "riot_api_failed"}),
      });
    });
    await page.route("**/search/**/matches*", async (route) => {
      await route.fulfill({status: 200, contentType: "application/json", body: '{"data":[],"meta":{"page":1,"limit":20,"total":0,"last_page":1}}'});
    });
    await page.route("**/live-game/**/stream", async (route) => {
      await route.fulfill({status: 200, headers: {"content-type": "text/event-stream"}, body: ""});
    });

    await page.goto(riotAccountUrl());

    // LiveGameSlot returns null when targetPuuid is null — neither live game text nor buttons
    await page.waitForTimeout(2_000);
    await expect(page.getByText("No live game.")).toHaveCount(0);
    await expect(page.getByText("Checking for live game")).toHaveCount(0);
  });
});
