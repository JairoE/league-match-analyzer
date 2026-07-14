"use client";

import {useEffect, useRef, useState} from "react";
import styles from "./ChatPanel.module.css";
import type {ChatMessage} from "../../lib/types/chat";

type ChatPanelProps = {
  isOpen: boolean;
  onClose: () => void;
  messages: ChatMessage[];
  isStreaming: boolean;
  toolActivity: string | null;
  error: string | null;
  onSend: (text: string) => void;
};

/**
 * Fixed-position coach chat drawer. The transcript lives in the parent
 * page's useChat instance, so closing the drawer preserves it.
 */
export default function ChatPanel({
  isOpen,
  onClose,
  messages,
  isStreaming,
  toolActivity,
  error,
  onSend,
}: ChatPanelProps) {
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, toolActivity]);

  if (!isOpen) return null;

  const submit = () => {
    const text = draft.trim();
    if (!text || isStreaming) return;
    setDraft("");
    onSend(text);
  };

  return (
    <aside className={styles.drawer} data-testid="chat-panel">
      <div className={styles.header}>
        <h3 className={styles.title}>Coach Chat</h3>
        <button
          className={styles.close}
          onClick={onClose}
          aria-label="Close chat"
        >
          &times;
        </button>
      </div>

      <div className={styles.messages} ref={scrollRef}>
        {messages.length === 0 ? (
          <p className={styles.emptyHint}>
            Ask about your recent games, your stats, or what to work on next —
            the coach looks up your data as it answers.
          </p>
        ) : null}
        {messages.map((message, index) => (
          <div
            key={index}
            className={
              message.role === "user" ? styles.userBubble : styles.coachBubble
            }
            data-testid={`chat-message-${message.role}`}
          >
            {message.content}
            {message.role === "assistant" &&
            isStreaming &&
            index === messages.length - 1 ? (
              <span className={styles.caret} aria-hidden />
            ) : null}
          </div>
        ))}
        {toolActivity ? (
          <p className={styles.toolActivity} data-testid="chat-tool-activity">
            {toolActivity}
          </p>
        ) : null}
        {error ? (
          <p className={styles.error} data-testid="chat-error">
            {error}
          </p>
        ) : null}
      </div>

      <div className={styles.inputRow}>
        <textarea
          className={styles.input}
          data-testid="chat-input"
          placeholder="Ask your coach…"
          rows={2}
          maxLength={4000}
          value={draft}
          disabled={isStreaming}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <button
          className={styles.send}
          data-testid="chat-send"
          onClick={submit}
          disabled={isStreaming || !draft.trim()}
        >
          Send
        </button>
      </div>
    </aside>
  );
}
