"use client";

import {useEffect, useMemo, useRef, useState} from "react";
import type {LiveGameData} from "../types/live-game";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 5_000;

type LiveGameState = {
  liveGame: LiveGameData | null;
  isLive: boolean;
};

export function useLiveGame(
  puuid: string | null
): LiveGameState {
  const [liveGame, setLiveGame] = useState<LiveGameData | null>(
    null
  );
  const retriesRef = useRef(0);

  useEffect(() => {
    if (!puuid) return;

    let es: EventSource | null = null;
    let retryTimeout: ReturnType<typeof setTimeout> | null =
      null;
    let cancelled = false;

    function connect() {
      if (cancelled) return;

      const base = API_BASE_URL.endsWith("/")
        ? API_BASE_URL.slice(0, -1)
        : API_BASE_URL;
      const url = `${base}/live-game/${puuid}/stream`;

      console.debug("[useLiveGame] connecting", {puuid});
      es = new EventSource(url);

      es.addEventListener("live_game", (event) => {
        retriesRef.current = 0;
        try {
          const data = JSON.parse(
            event.data
          ) as LiveGameData;
          setLiveGame(data);
        } catch (err) {
          console.debug("[useLiveGame] parse error", {err});
        }
      });

      es.addEventListener("not_in_game", () => {
        retriesRef.current = 0;
        setLiveGame(null);
      });

      es.addEventListener("error", () => {
        console.debug("[useLiveGame] error event", {puuid});
      });

      es.onerror = () => {
        if (cancelled) return;
        es?.close();
        es = null;

        if (retriesRef.current < MAX_RETRIES) {
          retriesRef.current += 1;
          console.debug("[useLiveGame] reconnecting", {
            attempt: retriesRef.current,
          });
          retryTimeout = setTimeout(connect, RETRY_DELAY_MS);
        } else {
          console.debug("[useLiveGame] max retries reached");
          setLiveGame(null);
        }
      };
    }

    connect();

    return () => {
      cancelled = true;
      es?.close();
      if (retryTimeout) clearTimeout(retryTimeout);
      retriesRef.current = 0;
      setLiveGame(null);
    };
  }, [puuid]);

  // When puuid is null, always report not live regardless of
  // stale state that may linger until the cleanup runs.
  const result = useMemo<LiveGameState>(() => {
    if (!puuid) return {liveGame: null, isLive: false};
    return {liveGame, isLive: liveGame !== null};
  }, [puuid, liveGame]);

  return result;
}
