"use client";

import styles from "./ChatButton.module.css";

type ChatButtonProps = {
  isOpen: boolean;
  disabled: boolean;
  onClick: () => void;
};

/** SubHeader action that toggles the coach chat drawer. */
export default function ChatButton({
  isOpen,
  disabled,
  onClick,
}: ChatButtonProps) {
  return (
    <button
      className={styles.button}
      onClick={onClick}
      disabled={disabled}
      data-testid="chat-button"
    >
      {isOpen ? "Close Coach" : "Ask Coach"}
    </button>
  );
}
