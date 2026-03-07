"use client";

import {useLiveGame} from "./useLiveGame";

/**
 * Gates live-game fetch until matches are ready. Call only when
 * matches have finished loading to avoid overlapping requests.
 */
export function useLiveGameWhenReady(
  puuid: string | null,
  matchesReady: boolean
) {
  const effectivePuuid = matchesReady ? puuid : null;
  return useLiveGame(effectivePuuid);
}
