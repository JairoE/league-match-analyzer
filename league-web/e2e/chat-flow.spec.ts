// Coach chat flow: streamed SSE answer with tool activity, and error surface.
//
// route.fulfill delivers a body all at once, which would collapse the
// streaming behavior we want to test — so the chat endpoint is mocked by
// overriding window.fetch with a ReadableStream that emits timed chunks.

import {test, expect, type Page} from "@playwright/test";
import {gotoAccountAndWait, mockRiotAccountRoutes} from "./helpers";

type SseFrame = {delay: number; data: string};

function frame(delay: number, event: string, data: object): SseFrame {
  return {delay, data: `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`};
}

async function mockChatStream(page: Page, frames: SseFrame[]) {
  await mockChatStreamSequence(page, [frames]);
}

// Serve a different frame-set per successive /chat/stream call. Calls past
// the end of the sequence reuse the last entry.
async function mockChatStreamSequence(page: Page, sequence: SseFrame[][]) {
  await page.addInitScript((streamSequence: SseFrame[][]) => {
    const originalFetch = window.fetch.bind(window);
    let call = 0;
    window.fetch = async (input, init) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof Request
            ? input.url
            : String(input);
      if (!url.includes("/chat/stream")) {
        return originalFetch(input, init);
      }
      const frames =
        streamSequence[Math.min(call, streamSequence.length - 1)];
      call += 1;
      const encoder = new TextEncoder();
      const stream = new ReadableStream<Uint8Array>({
        async start(controller) {
          for (const item of frames) {
            await new Promise((resolve) => setTimeout(resolve, item.delay));
            controller.enqueue(encoder.encode(item.data));
          }
          controller.close();
        },
      });
      return new Response(stream, {
        status: 200,
        headers: {"Content-Type": "text/event-stream"},
      });
    };
  }, sequence);
}

test.describe("Coach chat flow", () => {
  test.beforeEach(async ({page}) => {
    await mockRiotAccountRoutes(page);
  });

  test("send → tool activity → streamed answer", async ({page}) => {
    await mockChatStream(page, [
      frame(50, "tool_call", {
        name: "get_action_stats",
        label: "Crunching win-probability stats…",
      }),
      // Long gap so the activity indicator is observable
      frame(900, "tool_result", {name: "get_action_stats", ok: true}),
      frame(50, "token", {text: "Your dragon "}),
      frame(50, "token", {text: "control is improving."}),
      frame(50, "done", {finish_reason: "stop", rounds: 1}),
    ]);
    await gotoAccountAndWait(page);

    await page.getByTestId("chat-button").click();
    await expect(page.getByTestId("chat-panel")).toBeVisible();

    await page.getByTestId("chat-input").fill("How is my dragon control?");
    await page.getByTestId("chat-send").click();

    // User bubble appears immediately; tool activity during the gap
    await expect(page.getByTestId("chat-message-user")).toHaveText(
      "How is my dragon control?"
    );
    await expect(page.getByTestId("chat-tool-activity")).toHaveText(
      "Crunching win-probability stats…"
    );
    // Input is locked while streaming
    await expect(page.getByTestId("chat-input")).toBeDisabled();

    // Full streamed answer lands in the assistant bubble
    await expect(page.getByTestId("chat-message-assistant")).toHaveText(
      "Your dragon control is improving.",
      {timeout: 10_000}
    );
    await expect(page.getByTestId("chat-tool-activity")).not.toBeVisible();
    await expect(page.getByTestId("chat-input")).toBeEnabled();
  });

  test("transcript survives closing and reopening the drawer", async ({
    page,
  }) => {
    await mockChatStream(page, [
      frame(30, "token", {text: "Hi!"}),
      frame(30, "done", {finish_reason: "stop", rounds: 0}),
    ]);
    await gotoAccountAndWait(page);

    await page.getByTestId("chat-button").click();
    await page.getByTestId("chat-input").fill("Hello");
    await page.getByTestId("chat-send").click();
    await expect(page.getByTestId("chat-message-assistant")).toHaveText("Hi!");

    await page.getByRole("button", {name: "Close chat"}).click();
    await expect(page.getByTestId("chat-panel")).not.toBeVisible();

    await page.getByTestId("chat-button").click();
    await expect(page.getByTestId("chat-message-user")).toHaveText("Hello");
    await expect(page.getByTestId("chat-message-assistant")).toHaveText("Hi!");
  });

  test("error event surfaces an error and a fallback bubble", async ({
    page,
  }) => {
    await mockChatStream(page, [
      frame(50, "error", {detail: "chat_failed"}),
    ]);
    await gotoAccountAndWait(page);

    await page.getByTestId("chat-button").click();
    await page.getByTestId("chat-input").fill("Hello?");
    await page.getByTestId("chat-send").click();

    await expect(page.getByTestId("chat-error")).toHaveText(
      "The coach could not answer. Please try again."
    );
    await expect(page.getByTestId("chat-message-assistant")).toHaveText(
      "Something went wrong. Please try again."
    );
    await expect(page.getByTestId("chat-input")).toBeEnabled();
  });

  test("empty completion recovers and does not brick the next turn", async ({
    page,
  }) => {
    // First turn: a clean `done` with zero tokens. Second turn: real tokens.
    // Regression: the empty assistant bubble must not be POSTed back (the
    // backend rejects empty content and would 422 every later message).
    await mockChatStreamSequence(page, [
      [frame(50, "done", {finish_reason: "stop", rounds: 0})],
      [
        frame(50, "token", {text: "Second answer."}),
        frame(50, "done", {finish_reason: "stop", rounds: 0}),
      ],
    ]);
    await gotoAccountAndWait(page);

    await page.getByTestId("chat-button").click();
    await page.getByTestId("chat-input").fill("First question");
    await page.getByTestId("chat-send").click();

    // Blank completion is replaced by a fallback, not left empty
    await expect(
      page.getByTestId("chat-message-assistant")
    ).toHaveText("I couldn't generate a response. Please try rephrasing.");
    await expect(page.getByTestId("chat-input")).toBeEnabled();

    // Second turn succeeds — no 422 lockout from the empty prior bubble
    await page.getByTestId("chat-input").fill("Second question");
    await page.getByTestId("chat-send").click();
    await expect(
      page.getByTestId("chat-message-assistant").last()
    ).toHaveText("Second answer.");
    await expect(page.getByTestId("chat-error")).not.toBeVisible();
  });
});
