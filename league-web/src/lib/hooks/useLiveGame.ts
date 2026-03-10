"use client";

import {useCallback, useEffect, useMemo, useState} from "react";
import {getStaleMessage} from "../stale-message";
import type {LiveGameData} from "../types/live-game";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export type LiveGameStatus =
  | "idle"
  | "connecting"
  | "live"
  | "not_in_game"
  | "error";

export type LiveGameState = {
  liveGame: LiveGameData | null;
  isLive: boolean;
  status: LiveGameStatus;
  retry: () => void;
  liveGameWarning: string | null;
};

type LiveGameErrorPayload = {
  status?: number;
  error_message?: string;
};

function getLiveGameWarningForStatus(status: number | null): string | null {
  if (status === 401) {
    return getStaleMessage("riot_unavailable");
  }
  if (status === 502) {
    return "Error: please try again in a few minutes.";
  }
  return getStaleMessage("riot_unavailable");
}

export function useLiveGame(puuid: string | null): LiveGameState {
  const [liveGame, setLiveGame] = useState<LiveGameData | null>(null);
  const [status, setStatus] = useState<LiveGameStatus>("idle");
  const [attemptKey, setAttemptKey] = useState(0);
  const [liveGameWarning, setLiveGameWarning] = useState<string | null>(null);

  const retry = useCallback(() => {
    setAttemptKey((k) => k + 1);
  }, []);

  useEffect(() => {
    if (!puuid) return;

    let es: EventSource | null = null;
    let cancelled = false;

    const tid = setTimeout(() => {
      if (!cancelled) {
        setStatus("connecting");
        setLiveGame(null);
        setLiveGameWarning(null);
      }
    }, 0);

    const base = API_BASE_URL.endsWith("/")
      ? API_BASE_URL.slice(0, -1)
      : API_BASE_URL;
    const url = `${base}/live-game/${puuid}/stream`;

    console.debug("[useLiveGame] connecting", {puuid, attemptKey});
    es = new EventSource(url);

    function closeAndDone(newStatus: LiveGameStatus) {
      if (cancelled) return;
      es?.close();
      es = null;
      setStatus(newStatus);
      if (newStatus !== "live") setLiveGame(null);
      console.debug("[useLiveGame] closed", {puuid, newStatus});
    }

    es.addEventListener("live_game", (event) => {
      try {
        const data = JSON.parse(event.data) as LiveGameData;
        setLiveGame(data);
        setLiveGameWarning(null);
        closeAndDone("live");
      } catch (err) {
        console.debug("[useLiveGame] parse error", {err});
        closeAndDone("error");
      }
    });

    es.addEventListener("not_in_game", () => {
      setLiveGameWarning(null);
      closeAndDone("not_in_game");
    });

    es.addEventListener("error", (event) => {
      console.debug("[useLiveGame] error event", {puuid});
      try {
        const msg = event as MessageEvent<string>;
        const data = JSON.parse(msg.data) as LiveGameErrorPayload;
        const rawStatus = data?.status;
        const status =
          typeof rawStatus === "number" && Number.isFinite(rawStatus) ? rawStatus : null;
        const warning = getLiveGameWarningForStatus(status);
        setLiveGameWarning(warning);
      } catch (err) {
        console.debug("[useLiveGame] error event parse failed", {err});
        setLiveGameWarning(getLiveGameWarningForStatus(null));
      }
      closeAndDone("error");
    });

    es.onerror = () => {
      if (cancelled) return;
      console.debug("[useLiveGame] connection error", {puuid});
      setLiveGameWarning(getLiveGameWarningForStatus(null));
      closeAndDone("error");
    };

    return () => {
      cancelled = true;
      clearTimeout(tid);
      es?.close();
      es = null;
      setLiveGame(null);
      setStatus("idle");
      setLiveGameWarning(null);
    };
  }, [puuid, attemptKey]);

  const result = useMemo<LiveGameState>(() => {
    if (!puuid)
      return {
        liveGame: null,
        isLive: false,
        status: "idle",
        retry,
        liveGameWarning: null,
      };
    return {
      liveGame,
      isLive: status === "live" && liveGame !== null,
      status,
      retry,
      liveGameWarning,
    };
  }, [puuid, liveGame, status, retry, liveGameWarning]);

  return result;
}
