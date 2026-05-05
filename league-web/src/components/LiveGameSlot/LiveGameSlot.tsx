"use client";

import dynamic from "next/dynamic";
import type {LiveGameData} from "../../lib/types/live-game";
import type {LiveGameStatus} from "../../lib/hooks/useLiveGame";
import {DynamicImportBoundary} from "../common/DynamicImportBoundary";
import styles from "./LiveGameSlot.module.css";

const LiveGameCard = dynamic(
  () => import("../LiveGameCard/LiveGameCard"),
  {
    ssr: false,
    loading: () => (
      <div className={styles.box}>
        <span className={styles.message}>Loading live game…</span>
      </div>
    ),
  }
);

type LiveGameSlotProps = {
  status: LiveGameStatus;
  liveGame: LiveGameData | null;
  targetPuuid: string | null;
  onRetry: () => void;
};

export default function LiveGameSlot({
  status,
  liveGame,
  targetPuuid,
  onRetry,
}: LiveGameSlotProps) {
  if (!targetPuuid) return null;
  if (status === "idle") return null;

  if (status === "live" && liveGame) {
    return (
      <DynamicImportBoundary
        fallback={
          <div className={styles.box}>
            <span className={styles.message}>Live game unavailable.</span>
          </div>
        }
      >
        <LiveGameCard game={liveGame} targetPuuid={targetPuuid} />
      </DynamicImportBoundary>
    );
  }

  if (status === "connecting") {
    return (
      <div className={styles.box}>
        <span className={styles.message}>Checking for live game…</span>
      </div>
    );
  }

  if (status === "not_in_game") {
    return (
      <div className={styles.box}>
        <span className={styles.message}>No live game.</span>
        <button
          type="button"
          className={styles.button}
          onClick={onRetry}
        >
          Fetch live game
        </button>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className={styles.box}>
        <span className={styles.message}>Please try again.</span>
        <button
          type="button"
          className={styles.button}
          onClick={onRetry}
        >
          Fetch live game
        </button>
      </div>
    );
  }

  return null;
}
