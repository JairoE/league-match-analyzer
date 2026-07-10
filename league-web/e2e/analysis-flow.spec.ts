// AI Coach flow: enqueue → poll → panel, cached result, and timeout message.

import {test, expect, type Page} from "@playwright/test";
import {gotoAccountAndWait, mockRiotAccountRoutes} from "./helpers";
import {ANALYSIS_RESPONSE} from "./fixtures/analysis";

type AnalysisMockOptions = {
  postStatus?: "enqueued" | "already_exists";
  nullPollsBeforeResult?: number;
  alwaysNull?: boolean;
};

/**
 * Mock the analysis endpoints. GET returns null for the first
 * `nullPollsBeforeResult` calls (simulating a job still running),
 * then the full fixture — unless `alwaysNull` is set.
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
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          status: postStatus,
          analysis_id:
            postStatus === "already_exists" ? ANALYSIS_RESPONSE.id : null,
          champion_name: ANALYSIS_RESPONSE.champion_name,
        }),
      });
      return;
    }
    getCalls += 1;
    const ready = !alwaysNull && getCalls > nullPollsBeforeResult;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: ready ? JSON.stringify(ANALYSIS_RESPONSE) : "null",
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

    // Most-played champion from fixtures is Yasuo (2 ranked matches)
    const button = page.getByTestId("ai-coach-button");
    await expect(button).toHaveText(/AI Coach: Yasuo/);

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
});
