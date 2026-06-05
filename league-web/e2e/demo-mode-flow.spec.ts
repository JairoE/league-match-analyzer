// Demo mode (backend-free) end-to-end flow.
//
// Proves the app works as a standalone static deploy: with demo mode enabled
// and NO backend / API mocking at all, a user can sign in, land on /home, and
// see their rank + match history served entirely from the bundled dataset.
//
// Demo mode is toggled at runtime via localStorage (see resolve-mock.ts) so this
// runs against a plain `npm run dev` with no NEXT_PUBLIC_DEMO_MODE rebuild.

import {test, expect, type Page} from "@playwright/test";

const DEMO_MODE_STORAGE_KEY = "league.demoMode";

// Path patterns that would only ever be requested if the app tried to reach the
// FastAPI backend. In demo mode none of these should leave the browser.
function isBackendApiCall(urlString: string): boolean {
  let pathname: string;
  try {
    pathname = new URL(urlString).pathname;
  } catch {
    return false;
  }
  return (
    /^\/users\/sign_(in|up)$/.test(pathname) ||
    pathname.startsWith("/search/") ||
    pathname.startsWith("/riot-accounts/") ||
    pathname.startsWith("/rank/") ||
    pathname.startsWith("/champions") ||
    pathname.startsWith("/live-game/") ||
    /\/matches(\/|$)/.test(pathname)
  );
}

function signInForm(page: Page) {
  return page
    .locator("form")
    .filter({has: page.getByRole("heading", {name: "Sign in"})});
}

test.describe("Demo mode — full user flow without a backend", () => {
  test.beforeEach(async ({page}) => {
    // Enable demo mode before any app script runs, on every navigation.
    await page.addInitScript((key) => {
      window.localStorage.setItem(key, "true");
    }, DEMO_MODE_STORAGE_KEY);
  });

  test("sign in, land on home, and view match history from bundled data", async ({
    page,
  }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (err) => pageErrors.push(err.message));

    const backendCalls: string[] = [];
    page.on("request", (req) => {
      if (isBackendApiCall(req.url())) backendCalls.push(req.url());
    });

    // 1. Sign in with the demo credentials (any input is accepted in demo mode).
    await page.goto("/auth");
    const form = signInForm(page);
    await form.getByLabel("Summoner name").fill("DemoSummoner#NA1");
    await form.getByLabel("Email").fill("demo@league-analyzer.gg");
    await form.getByRole("button", {name: "Sign in"}).click();

    // 2. Redirected to the signed-in home page.
    await page.waitForURL("**/home");
    await expect(
      page.getByRole("heading", {name: "DemoSummoner"})
    ).toBeVisible({timeout: 10_000});

    // 3. Rank subtitle is rendered from the bundled rank payload.
    await expect(page.getByText(/PLATINUM IV/)).toBeVisible();

    // 4. Match history renders: 2 Ranked Solo + 1 Normal Draft + 1 ARAM.
    await expect(page.getByRole("cell", {name: "Ranked Solo"})).toHaveCount(2, {
      timeout: 10_000,
    });
    await expect(page.getByRole("cell", {name: "Normal Draft"})).toHaveCount(1);
    await expect(page.getByRole("cell", {name: "ARAM"})).toHaveCount(1);

    // 5. Summary bar reflects the demo outcomes (3 wins, 1 loss).
    await expect(page.getByText("3W")).toBeVisible();
    await expect(page.getByText("1L")).toBeVisible();

    // 6. Live game slot resolves to "not in game" (no SSE backend needed).
    await expect(page.getByText("No live game.")).toBeVisible({timeout: 8_000});

    // 7. The whole flow happened with ZERO backend API requests.
    expect(backendCalls).toEqual([]);

    const realErrors = pageErrors.filter(
      (e) => !e.includes("Warning:") && !e.includes("hydrat")
    );
    expect(realErrors).toEqual([]);
  });

  test("expanding a match loads champion + timeline detail from bundled data", async ({
    page,
  }) => {
    const backendCalls: string[] = [];
    page.on("request", (req) => {
      if (isBackendApiCall(req.url())) backendCalls.push(req.url());
    });

    await page.goto("/auth");
    const form = signInForm(page);
    await form.getByLabel("Summoner name").fill("DemoSummoner#NA1");
    await form.getByLabel("Email").fill("demo@league-analyzer.gg");
    await form.getByRole("button", {name: "Sign in"}).click();

    await page.waitForURL("**/home");

    // Expand the first match row to trigger champion/timeline fetches.
    const firstRow = page.getByRole("cell", {name: "Ranked Solo"}).first();
    await expect(firstRow).toBeVisible({timeout: 10_000});
    await firstRow.click();

    // Detail expands without errors and still no backend traffic.
    await expect(page.getByText("EnemyZed")).toBeVisible({timeout: 8_000});
    expect(backendCalls).toEqual([]);
  });

  test("searching the demo Riot ID returns its match history", async ({
    page,
  }) => {
    await page.goto("/riot-account/DemoSummoner%23NA1");

    await expect(page.getByRole("cell", {name: "Ranked Solo"})).toHaveCount(2, {
      timeout: 10_000,
    });
    await expect(page.getByRole("cell", {name: "ARAM"})).toHaveCount(1);
  });

  test("searching any other summoner shows no results (gated)", async ({
    page,
  }) => {
    await page.goto("/riot-account/SomeoneElse%23EUW");

    await expect(
      page.getByText(/No search results for the summoner/i)
    ).toBeVisible({timeout: 10_000});

    // The demo dataset must NOT leak into an unrelated search.
    await expect(page.getByRole("cell", {name: "Ranked Solo"})).toHaveCount(0);
  });

  test("signing in with the wrong credentials is rejected", async ({page}) => {
    await page.goto("/auth");
    const form = signInForm(page);
    await form.getByLabel("Summoner name").fill("WrongName#NA1");
    await form.getByLabel("Email").fill("nobody@example.com");
    await form.getByRole("button", {name: "Sign in"}).click();

    // Stays on the auth page and surfaces the demo-credentials hint.
    await expect(page.getByText(/Demo mode: sign in as/i)).toBeVisible({
      timeout: 8_000,
    });
    await expect(page).toHaveURL(/\/auth$/);
  });
});
