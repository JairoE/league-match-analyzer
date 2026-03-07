"use client";

import {useEffect, useMemo, useState} from "react";
import {apiGet} from "../api";
import type {RankInfo} from "../types/rank";

const LOG_TAG = "useRank";

function formatRankSubtitle(rank: RankInfo | null): string {
  if (!rank) return "Rank data unavailable";
  return `${rank.queueType ?? "Ranked"} · ${rank.tier ?? "Unranked"} ${rank.rank ?? ""} · ${rank.leaguePoints ?? 0} LP`;
}

type UseRankOptions = {
  refreshIndex?: number;
};

export function useRank(
  riotAccountId: string | null,
  options?: UseRankOptions
): {rank: RankInfo | null; rankSubtitle: string} {
  const {refreshIndex = 0} = options ?? {};
  const [rank, setRank] = useState<RankInfo | null>(null);

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
        console.debug(`[${LOG_TAG}] fetch done`, {riotAccountId});
      } catch (err) {
        console.debug(`[${LOG_TAG}] fetch failed`, {riotAccountId, err});
        if (!isActive) return;
        setRank(null);
      }
    };

    void loadRank();
    return () => {
      isActive = false;
    };
  }, [riotAccountId, refreshIndex]);

  const rankSubtitle = useMemo(() => formatRankSubtitle(rank), [rank]);
  return {rank, rankSubtitle};
}
