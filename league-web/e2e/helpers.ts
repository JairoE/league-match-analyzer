import {expect, type Page} from "@playwright/test";
import {
  ACCOUNT_RESPONSE,
  PAGE_1_RESPONSE,
  PAGE_2_RESPONSE,
  TEST_RIOT_ID,
} from "./fixtures/matches";

/**
 * Wire up all API route mocks needed for the riot-account page.
 * Intercepts by suffix so tests work regardless of NEXT_PUBLIC_API_BASE_URL.
 */
export async function mockRiotAccountRoutes(
  page: Page,
  overrides: {page2?: boolean} = {}
) {
  // Account lookup — echoes the searched riot id with a distinct account
  // id per id, so tests can navigate between accounts meaningfully.
  await page.route("**/search/**/account", async (route) => {
    const match = route.request().url().match(/\/search\/([^/]+)\/account/);
    const riotId = match
      ? decodeURIComponent(match[1])
      : ACCOUNT_RESPONSE.riot_id;
    const body =
      riotId === ACCOUNT_RESPONSE.riot_id
        ? ACCOUNT_RESPONSE
        : {...ACCOUNT_RESPONSE, id: `account-${riotId}`, riot_id: riotId};
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });

  // Match list — page 1 and page 2
  await page.route("**/search/**/matches*", async (route) => {
    const url = route.request().url();
    const isPage2 = url.includes("page=2");
    const response = isPage2 && overrides.page2 ? PAGE_2_RESPONSE : PAGE_1_RESPONSE;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(response),
    });
  });

  // Rank endpoint (optional — returns 404 gracefully)
  await page.route("**/riot-accounts/**/rank*", async (route) => {
    await route.fulfill({status: 404, body: "{}"});
  });

  // Live game SSE — immediately signals "not in game"
  await page.route("**/live-game/**/stream", async (route) => {
    await route.fulfill({
      status: 200,
      headers: {
        "content-type": "text/event-stream",
        "cache-control": "no-cache",
      },
      body: "event: not_in_game\ndata: {}\n\n",
    });
  });
}

/** Navigate to the riot-account page for the test user */
export function riotAccountUrl(): string {
  return `/riot-account/${TEST_RIOT_ID}`;
}

/**
 * Navigate to the riot-account page and wait until the matches table has
 * rendered its first row (a Ranked Solo cell from the fixture).
 */
export async function gotoAccountAndWait(page: Page) {
  await page.goto(riotAccountUrl());
  await expect(
    page.getByRole("cell", {name: "Ranked Solo"}).first()
  ).toBeVisible({timeout: 10_000});
}
