// AI Coach flow: enqueue → poll → panel, cached result, and timeout message.

import {test, expect, type Page} from "@playwright/test";
import {gotoAccountAndWait, mockRiotAccountRoutes} from "./helpers";
import {ANALYSIS_RESPONSE} from "./fixtures/analysis";

type AnalysisMockOptions = {
  postStatus?: "enqueued" | "already_exists";
  nullPollsBeforeResult?: number;
  alwaysNull?: boolean;
};

// Champion ids from e2e/fixtures/matches.ts participants
const CHAMPION_NAMES: Record<number, string> = {
  157: "Yasuo",
  238: "Zed",
  99: "Lux",
};

/**
 * Mock the analysis endpoints, echoing the requested champion. GET
 * returns null for the first `nullPollsBeforeResult` calls (simulating
 * a job still running), then the fixture — unless `alwaysNull` is set.
 */
async function mockAnalysisRoutes(
  page: Page,
  {
    postStatus = "enqueued",
    nullPollsBeforeResult = 1,
    alwaysNull = false,
  }: AnalysisMockOptions = {}
) {
  let getCalls = 0;
  await page.route("**/riot-accounts/**/analysis*", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON() as {champion_id: number};
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          status: postStatus,
          analysis_id:
            postStatus === "already_exists" ? ANALYSIS_RESPONSE.id : null,
          champion_name:
            CHAMPION_NAMES[body.champion_id] ?? ANALYSIS_RESPONSE.champion_name,
        }),
      });
      return;
    }
    getCalls += 1;
    const ready = !alwaysNull && getCalls > nullPollsBeforeResult;
    const url = new URL(route.request().url());
    const championName =
      url.searchParams.get("champion_name") ?? ANALYSIS_RESPONSE.champion_name;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: ready
        ? JSON.stringify({...ANALYSIS_RESPONSE, champion_name: championName})
        : "null",
    });
  });
}

test.describe("AI Coach analysis flow", () => {
  test.beforeEach(async ({page}) => {
    await mockRiotAccountRoutes(page);
  });

  test("happy path: click → analyzing → panel with recommendations", async ({
    page,
  }) => {
    await mockAnalysisRoutes(page, {nullPollsBeforeResult: 1});
    await gotoAccountAndWait(page);

    // Picker defaults to the most-played champion: Yasuo (2 ranked matches)
    const select = page.getByTestId("ai-coach-champion-select");
    await expect(select).toHaveValue("157");
    const button = page.getByTestId("ai-coach-button");
    await expect(button).toHaveText(/AI Coach/);

    await button.click();
    await expect(button).toHaveText(/Analyzing/);

    // First poll returns null, second returns the analysis (~4s)
    const panel = page.getByTestId("analysis-panel");
    await expect(panel).toBeVisible({timeout: 15_000});
    await expect(panel).toContainText("AI Coach: Yasuo");
    await expect(
      page.getByTestId("analysis-recommendation")
    ).toHaveCount(3);
    await expect(panel).toContainText("Based on 12 scored matches");

    // Dismiss via the X button
    await page.getByRole("button", {name: "Dismiss analysis"}).click();
    await expect(panel).not.toBeVisible();
  });

  test("cached path: already_exists loads panel without polling", async ({
    page,
  }) => {
    await mockAnalysisRoutes(page, {
      postStatus: "already_exists",
      nullPollsBeforeResult: 0,
    });
    await gotoAccountAndWait(page);

    await page.getByTestId("ai-coach-button").click();

    // No 2s polling loop — result should appear almost immediately
    await expect(page.getByTestId("analysis-panel")).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.getByTestId("analysis-recommendation")
    ).toHaveCount(3);
  });

  test("timeout message shows when no result materializes", async ({
    page,
  }) => {
    // already_exists + null GET exercises the timeout message without
    // waiting out the full 60s polling budget.
    await mockAnalysisRoutes(page, {
      postStatus: "already_exists",
      alwaysNull: true,
    });
    await gotoAccountAndWait(page);

    await page.getByTestId("ai-coach-button").click();

    const error = page.getByTestId("analysis-error");
    await expect(error).toBeVisible({timeout: 5000});
    await expect(error).toContainText(
      "Analysis is taking longer than expected"
    );
  });

  test("champion picker: analyze a non-most-played champion, then switch", async ({
    page,
  }) => {
    await mockAnalysisRoutes(page, {
      postStatus: "already_exists",
      nullPollsBeforeResult: 0,
    });
    await gotoAccountAndWait(page);

    // Pick Lux (1 game — not the default) and analyze her
    const select = page.getByTestId("ai-coach-champion-select");
    await select.selectOption("99");
    await page.getByTestId("ai-coach-button").click();

    const panel = page.getByTestId("analysis-panel");
    await expect(panel).toBeVisible({timeout: 5000});
    await expect(panel).toContainText("AI Coach: Lux");
    await expect(page.getByTestId("ai-coach-button")).toHaveText(
      "Hide AI Coach"
    );

    // Switch the picker back to Yasuo: the button offers a fresh analysis
    await select.selectOption("157");
    await expect(page.getByTestId("ai-coach-button")).toHaveText("AI Coach");
    await page.getByTestId("ai-coach-button").click();

    await expect(panel).toBeVisible({timeout: 5000});
    await expect(panel).toContainText("AI Coach: Yasuo");
  });
});
