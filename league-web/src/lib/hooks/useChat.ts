"use client";

import {useCallback, useEffect, useRef, useState} from "react";
import {buildApiErrorFromResponse} from "../errors/parse-api-error";
import {useAppError} from "../errors/error-store";
import {parseSseStream} from "../sse";
import type {
  ChatDoneData,
  ChatMessage,
  ChatTokenData,
  ChatToolCallData,
} from "../types/chat";

const LOG_TAG = "useChat";
const MAX_HISTORY_MESSAGES = 20;
const FAILURE_MESSAGE = "Something went wrong. Please try again.";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

type UseChatOptions = {
  championFocus?: string | null;
};

type UseChatResult = {
  messages: ChatMessage[];
  isStreaming: boolean;
  toolActivity: string | null;
  error: string | null;
  sendMessage: (text: string) => Promise<void>;
  reset: () => void;
};

function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

/**
 * Stateless coach chat: holds the transcript in memory, POSTs the full
 * history each turn, and streams the assistant's answer token-by-token
 * from the SSE response body.
 */
export function useChat(
  riotAccountId: string | null,
  options?: UseChatOptions
): UseChatResult {
  const championFocus = options?.championFocus ?? null;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [toolActivity, setToolActivity] = useState<string | null>(null);
  const {errorMessage, reportError, clearError} = useAppError("chat");
  const abortRef = useRef<AbortController | null>(null);

  // Abort any in-flight stream on unmount or account change.
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      abortRef.current = null;
    };
  }, [riotAccountId]);

  // Discard the transcript when the account changes (render-time
  // adjustment — setState in an effect body trips lint).
  const [lastAccountId, setLastAccountId] = useState(riotAccountId);
  if (riotAccountId !== lastAccountId) {
    setLastAccountId(riotAccountId);
    setMessages([]);
    setIsStreaming(false);
    setToolActivity(null);
  }

  const sendMessage = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!riotAccountId || !content || isStreaming) return;

      clearError();
      const userMessage: ChatMessage = {role: "user", content};
      const history: ChatMessage[] = [...messages, userMessage].slice(
        -MAX_HISTORY_MESSAGES
      );
      // Placeholder assistant message that tokens append into.
      setMessages([...history, {role: "assistant", content: ""}]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      const appendToAssistant = (delta: string) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === "assistant") {
            next[next.length - 1] = {
              role: "assistant",
              content: last.content + delta,
            };
          }
          return next;
        });
      };

      const failAssistant = () => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === "assistant" && last.content === "") {
            next[next.length - 1] = {
              role: "assistant",
              content: FAILURE_MESSAGE,
            };
          }
          return next;
        });
      };

      try {
        console.debug(`[${LOG_TAG}] send`, {riotAccountId});
        const res = await fetch(
          `${API_BASE_URL}/riot-accounts/${riotAccountId}/chat/stream`,
          {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              messages: history,
              champion_focus: championFocus,
            }),
            signal: controller.signal,
          }
        );
        if (!res.ok || !res.body) {
          const rawBody = res.body ? await res.text() : "";
          throw buildApiErrorFromResponse({
            url: res.url,
            method: "POST",
            status: res.status,
            statusText: res.statusText,
            rawBody,
          });
        }

        let sawDone = false;
        for await (const event of parseSseStream(res.body)) {
          if (event.event === "token") {
            const data = JSON.parse(event.data) as ChatTokenData;
            appendToAssistant(data.text);
          } else if (event.event === "tool_call") {
            const data = JSON.parse(event.data) as ChatToolCallData;
            setToolActivity(data.label);
          } else if (event.event === "tool_result") {
            setToolActivity(null);
          } else if (event.event === "done") {
            const data = JSON.parse(event.data) as ChatDoneData;
            console.debug(`[${LOG_TAG}] done`, data);
            sawDone = true;
          } else if (event.event === "error") {
            throw new Error("The coach could not answer. Please try again.");
          }
        }
        if (!sawDone) {
          throw new Error("The connection dropped before the answer finished.");
        }
      } catch (err) {
        if (isAbortError(err)) {
          console.debug(`[${LOG_TAG}] aborted`);
          return;
        }
        console.debug(`[${LOG_TAG}] error`, {err});
        failAssistant();
        reportError(err);
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
        setIsStreaming(false);
        setToolActivity(null);
      }
    },
    [
      riotAccountId,
      isStreaming,
      messages,
      championFocus,
      clearError,
      reportError,
    ]
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setMessages([]);
    setIsStreaming(false);
    setToolActivity(null);
    clearError();
  }, [clearError]);

  return {
    messages,
    isStreaming,
    toolActivity,
    // errorMessage is "" (not null) when the scope has no error
    error: errorMessage || null,
    sendMessage,
    reset,
  };
}
