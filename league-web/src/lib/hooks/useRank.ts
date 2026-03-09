"use client";

import {useEffect, useMemo, useState} from "react";
import {apiGet} from "../api";
import {isApiError} from "../errors/types";
import {getStaleMessage} from "../stale-message";
import type {RankInfo} from "../types/rank";

const LOG_TAG = "useRank";

function formatRankSubtitle(rank: RankInfo | null): string {
  if (!rank) return "Rank data unavailable";
  return `${rank.queueType ?? "Ranked"} · ${rank.tier ?? "Unranked"} ${rank.rank ?? ""} · ${rank.leaguePoints ?? 0} LP`;
}

function isRiotUnavailableStatus(err: unknown): boolean {
  if (!isApiError(err)) return false;
  const status = err.riotStatus ?? err.status;
  if (status == null) return false;
  if (status === 200 || status === 500) return false;
  return status >= 400;
}

type UseRankOptions = {
  refreshIndex?: number;
};

export function useRank(
  riotAccountId: string | null,
  options?: UseRankOptions
): {rank: RankInfo | null; rankSubtitle: string; rankStaleMessage: string | null} {
  const {refreshIndex = 0} = options ?? {};
  const [rank, setRank] = useState<RankInfo | null>(null);
  const [rankStaleReason, setRankStaleReason] = useState<string | null>(null);

  useEffect(() => {
    if (!riotAccountId) return;
    let isActive = true;

    const loadRank = async () => {
      console.debug(`[${LOG_TAG}] fetch start`, {riotAccountId});
      try {
        const rankResponse = await apiGet<RankInfo>(
          `/riot-accounts/${riotAccountId}/fetch_rank`,
          {cacheTtlMs: 60_000}
        );
        if (!isActive) return;
        setRank(rankResponse ?? null);
        setRankStaleReason(null);
        console.debug(`[${LOG_TAG}] fetch done`, {riotAccountId});
      } catch (err) {
        console.debug(`[${LOG_TAG}] fetch failed`, {riotAccountId, err});
        if (!isActive) return;
        setRank(null);
        setRankStaleReason(
          isRiotUnavailableStatus(err) ? "riot_unavailable" : null
        );
      }
    };

    void loadRank();
    return () => {
      isActive = false;
    };
  }, [riotAccountId, refreshIndex]);

  const rankSubtitle = useMemo(() => formatRankSubtitle(rank), [rank]);
  const rankStaleMessage = useMemo(
    () => getStaleMessage(rankStaleReason),
    [rankStaleReason]
  );
  return {rank, rankSubtitle, rankStaleMessage};
}
