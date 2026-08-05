// AI Coach flow: enqueue → poll → panel, cached result, and timeout message.

import {test, expect, type Page} from "@playwright/test";
import {
  gotoAccountAndWait,
  mockRiotAccountRoutes,
  riotAccountUrl,
} from "./helpers";
import {ANALYSIS_RESPONSE} from "./fixtures/analysis";
import {PAGE_1_RESPONSE} from "./fixtures/matches";

type AnalysisMockOptions = {
  postStatus?: "enqueued" | "already_exists";
  nullPollsBeforeResult?: number;
  alwaysNull?: boolean;
  championOptionsStatus?: number;
  championOptionsResponses?: AnalysisChampionFixture[][];
  // Call indexes (0-based, across the eligibility endpoint's own call
  // count) that should fail with a transient server error instead of
  // returning championOptionsResponses — simulates a re-poll attempt
  // hitting a 502/network error without aborting the repoll chain.
  championOptionsFailIndexes?: number[];
  requestedChampionIds?: number[];
};

type AnalysisChampionFixture = {
  champion_id: number;
  champion_name: string;
  scored_match_count: number;
  scored_action_count: number;
  corpus_example_count: number;
};

const ANALYZABLE_CHAMPIONS: AnalysisChampionFixture[] = [
  {
    champion_id: 99,
    champion_name: "Lux",
    scored_match_count: 15,
    scored_action_count: 40,
    corpus_example_count: 6,
  },
  {
    champion_id: 12,
    champion_name: "Alistar",
    scored_match_count: 12,
    scored_action_count: 35,
    corpus_example_count: 5,
  },
  {
    champion_id: 53,
    champion_name: "Blitzcrank",
    scored_match_count: 6,
    scored_action_count: 22,
    corpus_example_count: 5,
  },
];

const CHAMPION_NAMES: Record<number, string> = {
  12: "Alistar",
  53: "Blitzcrank",
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
    championOptionsStatus = 200,
    championOptionsResponses = [ANALYZABLE_CHAMPIONS],
    championOptionsFailIndexes = [],
    requestedChampionIds,
  }: AnalysisMockOptions = {}
) {
  let getCalls = 0;
  let championOptionsCalls = 0;
  await page.route("**/riot-accounts/**/analysis**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/analysis/champions")) {
      const callIndex = championOptionsCalls++;
      if (championOptionsFailIndexes.includes(callIndex)) {
        await route.fulfill({
          status: 502,
          contentType: "application/json",
          body: JSON.stringify({detail: "riot_api_failed"}),
        });
        return;
      }
      await route.fulfill({
        status: championOptionsStatus,
        contentType: "application/json",
        body:
          championOptionsStatus === 200
            ? JSON.stringify(
                championOptionsResponses[
                  Math.min(callIndex, championOptionsResponses.length - 1)
                ]
              )
            : "{}",
      });
      return;
    }
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON() as {champion_id: number};
      requestedChampionIds?.push(body.champion_id);
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

    // Picker defaults to the endpoint's first (most-scored) champion.
    const select = page.getByTestId("ai-coach-champion-select");
    await expect(select).toHaveValue("99");
    const button = page.getByTestId("ai-coach-button");
    await expect(button).toHaveText(/AI Coach/);

    await button.click();
    await expect(button).toHaveText(/Analyzing/);
    // The picker locks while a run is in flight — switching champions
    // mid-poll would misattribute the landing result.
    await expect(select).toBeDisabled();

    // First poll returns null, second returns the analysis (~4s)
    const panel = page.getByTestId("analysis-panel");
    await expect(panel).toBeVisible({timeout: 15_000});
    await expect(panel).toContainText("AI Coach: Lux");
    await expect(
      page.getByTestId("analysis-recommendation")
    ).toHaveCount(3);
    await expect(panel).toContainText("Based on 12 scored matches");

    // Dismiss via the X button
    await page.getByRole("button", {name: "Dismiss analysis"}).click();
    await expect(panel).not.toBeVisible();
  });

  test("picker lives in a dedicated AI Coach card, apart from the matches", async ({
    page,
  }) => {
    await mockAnalysisRoutes(page, {
      postStatus: "already_exists",
      nullPollsBeforeResult: 0,
    });
    await gotoAccountAndWait(page);

    // The champion picker + trigger live inside the AI Coach card, not the
    // top action bar next to Refresh — so it never reads as if it were
    // derived from the games shown below.
    const card = page.getByTestId("ai-coach-card");
    await expect(card).toBeVisible();
    await expect(card.getByTestId("ai-coach-champion-select")).toBeVisible();
    await expect(card.getByTestId("ai-coach-button")).toBeVisible();
    // The scope caption states the full-history basis explicitly.
    await expect(card).toContainText("full ranked history");
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

  test("champion picker uses eligible server options and switches", async ({
    page,
  }) => {
    const requestedChampionIds: number[] = [];
    await mockAnalysisRoutes(page, {
      postStatus: "already_exists",
      nullPollsBeforeResult: 0,
      requestedChampionIds,
      championOptionsResponses: [
        ANALYZABLE_CHAMPIONS,
        ANALYZABLE_CHAMPIONS.filter(
          (champion) => champion.champion_id !== 12
        ),
      ],
    });
    await gotoAccountAndWait(page);

    const select = page.getByTestId("ai-coach-champion-select");
    await expect(select.locator("option")).toHaveText([
      "Lux (15)",
      "Alistar (12)",
      "Blitzcrank (6)",
    ]);
    await expect(select.locator('option[value="238"]')).toHaveCount(0);

    // Alistar is provided by the eligibility endpoint, not the loaded matches.
    await select.selectOption("12");
    await page.getByTestId("ai-coach-button").click();

    const panel = page.getByTestId("analysis-panel");
    await expect(panel).toBeVisible({timeout: 5000});
    await expect(panel).toContainText("AI Coach: Alistar");
    await expect(page.getByTestId("ai-coach-button")).toHaveText(
      "Hide AI Coach"
    );

    // A server refresh can make the selected champion ineligible. The old
    // champion panel must disappear even though the select handler did not run.
    await page.getByRole("button", {name: "Refresh"}).click();
    await expect(select).toHaveValue("99");
    await expect(panel).not.toBeVisible();
    await expect(page.getByTestId("ai-coach-button")).toHaveText("AI Coach");
    await page.getByTestId("ai-coach-button").click();
    await expect(panel).toBeVisible({timeout: 5000});
    await expect(panel).toContainText("AI Coach: Lux");

    await select.selectOption("53");
    await page.getByTestId("ai-coach-button").click();
    await expect(panel).toContainText("AI Coach: Blitzcrank");
    expect(requestedChampionIds).toEqual([12, 99, 53]);
  });

  test("re-polls eligibility after a refresh so a newly-scored champion surfaces", async ({
    page,
  }) => {
    const two = ANALYZABLE_CHAMPIONS.slice(0, 2);
    const three = [
      ...two,
      {
        champion_id: 63,
        champion_name: "Brand",
        scored_match_count: 1,
        scored_action_count: 3,
        corpus_example_count: 0,
      },
    ];
    // Stay at two until the post-refresh re-poll (a later options call)
    // returns the freshly-scored Brand — so Brand arrives via the re-poll,
    // not the refresh fetch itself.
    await mockAnalysisRoutes(page, {
      championOptionsResponses: [two, two, two, three],
    });
    await gotoAccountAndWait(page);

    const select = page.getByTestId("ai-coach-champion-select");
    await expect(select.locator("option")).toHaveText([
      "Lux (15)",
      "Alistar (12)",
    ]);

    // A refresh ingests + scores recent matches asynchronously; the picker
    // re-polls and surfaces the newly-scored champion without a 2nd refresh.
    await page.getByRole("button", {name: "Refresh"}).click();

    await expect(select.locator('option[value="63"]')).toHaveText(
      "Brand (1)",
      {timeout: 12_000}
    );
  });

  test("re-poll arms on the first search, without a manual refresh", async ({
    page,
  }) => {
    // Regression: the re-poll gate used to require the *previous* account id
    // to equal the current one, which a first search (null -> uuid) can
    // never satisfy — so a freshly-scored champion never surfaced without
    // an explicit Refresh click. No Refresh button is touched below.
    const oneChampion = [ANALYZABLE_CHAMPIONS[0]];
    await mockAnalysisRoutes(page, {
      championOptionsResponses: [[], oneChampion],
    });
    await gotoAccountAndWait(page);

    const select = page.getByTestId("ai-coach-champion-select");
    await expect(select).toBeDisabled();
    await expect(select).toHaveText("No scored champions");

    // The mount-triggered re-poll (account becomes known for the first
    // time) should surface Lux without any further user action.
    await expect(select.locator('option[value="99"]')).toHaveText(
      "Lux (15)",
      {timeout: 12_000}
    );
    await expect(select).toBeEnabled();
  });

  test("a transient re-poll failure does not abort the remaining attempts", async ({
    page,
  }) => {
    // Regression: scheduleRepoll used to recurse only inside the try block,
    // so the first failed attempt (502/network error) permanently ended the
    // chain. Attempt 1 fails below; attempt 2 must still fire and land.
    const two = ANALYZABLE_CHAMPIONS.slice(0, 2);
    const three = [
      ...two,
      {
        champion_id: 63,
        champion_name: "Brand",
        scored_match_count: 1,
        scored_action_count: 3,
        corpus_example_count: 0,
      },
    ];
    await mockAnalysisRoutes(page, {
      championOptionsResponses: [two, two, three],
      championOptionsFailIndexes: [1],
    });
    await gotoAccountAndWait(page);

    const select = page.getByTestId("ai-coach-champion-select");
    await expect(select.locator("option")).toHaveText([
      "Lux (15)",
      "Alistar (12)",
    ]);

    // Attempt 1 (~5s) fails; attempt 2 (~10s) must still be scheduled and
    // surface Brand.
    await expect(select.locator('option[value="63"]')).toHaveText(
      "Brand (1)",
      {timeout: 16_000}
    );
  });

  test("an open analysis survives a re-poll reorder of the champion list", async ({
    page,
  }) => {
    // Regression: with no explicit pick, selectedChampion used to be plain
    // champions[0]. Re-polling exists because scoring changes
    // scored_match_count, which can reorder the server's list — a same-
    // length reorder silently swapped the selection, flipped
    // isAnalysisForSelectedChampion false, and made an open analysis panel
    // vanish with no message. handleAnalysisClick now pins the champion id
    // at request time so the open analysis survives the reorder.
    const luxFirst = ANALYZABLE_CHAMPIONS.slice(0, 2); // Lux (99), Alistar (12)
    const alistarFirst = [luxFirst[1], luxFirst[0]]; // same ids, reordered
    await mockAnalysisRoutes(page, {
      postStatus: "already_exists",
      nullPollsBeforeResult: 0,
      // Stay at luxFirst through the initial load and the refresh's own
      // fetch; the reorder only arrives via the post-refresh re-poll, so
      // this isolates the reorder scenario (not just "a re-poll happened").
      championOptionsResponses: [luxFirst, luxFirst, alistarFirst],
    });
    await gotoAccountAndWait(page);

    const select = page.getByTestId("ai-coach-champion-select");
    await expect(select).toHaveValue("99");

    // No explicit pick — the click analyzes the implicit first (highest-
    // scored) champion, Lux.
    await page.getByTestId("ai-coach-button").click();
    const panel = page.getByTestId("analysis-panel");
    await expect(panel).toBeVisible({timeout: 5000});
    await expect(panel).toContainText("AI Coach: Lux");

    // Refresh re-fetches (still luxFirst) and arms the re-poll; the re-poll
    // then returns the SAME two champions reordered (Alistar now outranks
    // Lux) — the open analysis must not vanish or flip to the new first
    // champion.
    await page.getByRole("button", {name: "Refresh"}).click();

    await expect(select.locator("option")).toHaveText(
      ["Alistar (12)", "Lux (15)"],
      {timeout: 12_000}
    );
    await expect(panel).toBeVisible();
    await expect(panel).toContainText("AI Coach: Lux");
    await expect(select).toHaveValue("99");
  });

  test("champion picker disables analysis and formats loading errors", async ({
    page,
  }) => {
    await mockAnalysisRoutes(page, {championOptionsStatus: 503});
    await gotoAccountAndWait(page);

    const select = page.getByTestId("ai-coach-champion-select");
    await expect(select).toBeDisabled();
    await expect(select).toHaveText("No scored champions");
    await expect(page.getByTestId("ai-coach-button")).toBeDisabled();
    await expect(
      page.getByText("Server error. Please try again later.")
    ).toBeVisible();
  });

  test("server eligibility remains available with no loaded matches", async ({
    page,
  }) => {
    // Registered after the beforeEach mock, so this empty list wins.
    await page.route("**/search/**/matches*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...PAGE_1_RESPONSE,
          data: [],
          meta: {...PAGE_1_RESPONSE.meta, total: 0, last_page: 1},
        }),
      });
    });
    await mockAnalysisRoutes(page);
    await page.goto(riotAccountUrl());

    await expect(page.getByText("Viewing matches for")).toBeVisible();
    const select = page.getByTestId("ai-coach-champion-select");
    await expect(select.locator("option")).toHaveText([
      "Lux (15)",
      "Alistar (12)",
      "Blitzcrank (6)",
    ]);
    await expect(page.getByTestId("ai-coach-button")).toBeEnabled();
  });

  test("no eligible champions disables the picker and analysis", async ({
    page,
  }) => {
    await mockAnalysisRoutes(page, {championOptionsResponses: [[]]});
    await gotoAccountAndWait(page);

    const select = page.getByTestId("ai-coach-champion-select");
    await expect(select).toBeDisabled();
    await expect(select).toHaveText("No scored champions");
    await expect(page.getByTestId("ai-coach-button")).toBeDisabled();
  });

  test("error path: failed POST shows an error, then retry succeeds", async ({
    page,
  }) => {
    let postCalls = 0;
    await page.route("**/riot-accounts/**/analysis**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname.endsWith("/analysis/champions")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(ANALYZABLE_CHAMPIONS),
        });
        return;
      }
      if (route.request().method() === "POST") {
        postCalls += 1;
        if (postCalls === 1) {
          await route.fulfill({
            status: 500,
            contentType: "application/json",
            body: JSON.stringify({detail: "internal error"}),
          });
        } else {
          await route.fulfill({
            status: 202,
            contentType: "application/json",
            body: JSON.stringify({
              status: "already_exists",
              analysis_id: ANALYSIS_RESPONSE.id,
              champion_name: ANALYSIS_RESPONSE.champion_name,
            }),
          });
        }
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(ANALYSIS_RESPONSE),
      });
    });
    await gotoAccountAndWait(page);

    const button = page.getByTestId("ai-coach-button");
    await button.click();
    await expect(page.getByTestId("analysis-error")).toBeVisible({
      timeout: 5000,
    });
    // The error belongs to the selected champion, so the button toggles.
    await expect(button).toHaveText("Hide AI Coach");
    await button.click();
    await expect(page.getByTestId("analysis-panel")).not.toBeVisible();

    // Retry: the second POST succeeds and the panel renders.
    await button.click();
    await expect(page.getByTestId("analysis-panel")).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.getByTestId("analysis-recommendation")
    ).toHaveCount(3);
  });

  test("switching accounts mid-poll abandons the old polling loop", async ({
    page,
  }) => {
    // Result becomes ready on the 3rd poll (~6s) — after the account
    // switch below, so a stale loop would render a foreign panel.
    await mockAnalysisRoutes(page, {nullPollsBeforeResult: 2});
    await gotoAccountAndWait(page);

    const button = page.getByTestId("ai-coach-button");
    await button.click();
    await expect(button).toHaveText(/Analyzing/);

    // Client-side navigation to another account: same page component,
    // new params — the in-flight poll loop must be invalidated.
    const search = page.getByPlaceholder("Search summoner (e.g. Name#TAG)");
    await search.fill("OtherUser#NA1");
    await search.press("Enter");

    await expect(
      page.getByRole("heading", {name: "OtherUser#NA1"})
    ).toBeVisible({timeout: 10_000});
    await expect(button).toHaveText("AI Coach", {timeout: 10_000});

    // Wait past the moment the abandoned loop's result would have landed.
    await page.waitForTimeout(7000);
    await expect(page.getByTestId("analysis-panel")).not.toBeVisible();
    await expect(button).toHaveText("AI Coach");
  });
});
