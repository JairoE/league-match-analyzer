"use client";

import {useState, useEffect, useRef} from "react";
import {apiGet} from "../../lib/api";
import {getMatchId} from "../../lib/match-utils";
import type {Champion} from "../../lib/types/champion";
import type {LaneStats, MatchDetail, MatchSummary, Participant} from "../../lib/types/match";
import type {RankBatchResponse, RankInfo} from "../../lib/types/rank";

type UseMatchDetailDataParams = {
  expandedMatchIds: Set<string>;
  matches: MatchSummary[];
  matchDetails: Record<string, MatchDetail>;
  getParticipantForMatch: (match: MatchSummary) => Participant | null;
  championIdsToLoad: number[];
};

export function useMatchDetailData({
  expandedMatchIds,
  matches,
  matchDetails,
  getParticipantForMatch,
  championIdsToLoad,
}: UseMatchDetailDataParams) {
  const [championById, setChampionById] = useState<Record<number, Champion>>({});
  const [rankByPuuid, setRankByPuuid] = useState<Record<string, RankInfo | null>>({});
  const [laneStatsByMatchId, setLaneStatsByMatchId] = useState<Record<string, LaneStats | null>>({});

  // Track which matchIds have already had rank/timeline fetched to avoid re-fetching
  const fetchedRankMatchIds = useRef<Set<string>>(new Set());
  const fetchedTimelineMatchIds = useRef<Set<string>>(new Set());

  // Champion fetch — only request IDs not already in championById
  useEffect(() => {
    const missingIds = championIdsToLoad.filter((id) => championById[id] == null);
    if (missingIds.length === 0) return;

    let isActive = true;

    void Promise.allSettled(
      missingIds.map(async (id) => {
        const champion = await apiGet<Champion>(`/champions/${id}`, {cacheTtlMs: 60_000});
        return {id, champion};
      })
    ).then((results) => {
      if (!isActive) return;
      const loaded = results
        .filter((r) => r.status === "fulfilled")
        .map((r) => (r as PromiseFulfilledResult<{id: number; champion: Champion}>).value);
      if (loaded.length === 0) return;
      setChampionById((prev) => {
        const next = {...prev};
        for (const {id, champion} of loaded) {
          if (prev[id] == null) next[id] = champion;
        }
        return Object.keys(next).length === Object.keys(prev).length ? prev : next;
      });
    });

    return () => {
      isActive = false;
    };
  }, [championIdsToLoad, championById]);

  // Rank fetch — fires for each newly expanded matchId
  useEffect(() => {
    if (expandedMatchIds.size === 0) return;

    const controllers: AbortController[] = [];

    for (const matchId of expandedMatchIds) {
      if (fetchedRankMatchIds.current.has(matchId)) continue;
      const detail = matchDetails[matchId];
      if (!detail?.info?.participants) continue;

      const missing = detail.info.participants
        .map((p) => p.puuid)
        .filter((puuid): puuid is string => !!puuid && rankByPuuid[puuid] === undefined);

      if (missing.length === 0) {
        fetchedRankMatchIds.current.add(matchId);
        continue;
      }

      fetchedRankMatchIds.current.add(matchId);
      let isActive = true;
      controllers.push({abort: () => { isActive = false; }} as AbortController);

      void apiGet<RankBatchResponse>(`/rank/batch?puuids=${missing.join(",")}`, {
        cacheTtlMs: 3_600_000,
      }).then((data) => {
        if (!isActive) return;
        setRankByPuuid((prev) => ({...prev, ...data}));
      }).catch(() => {/* silently ignore rank errors */});
    }

    return () => {
      for (const c of controllers) c.abort();
    };
  }, [expandedMatchIds, matchDetails]); // eslint-disable-line react-hooks/exhaustive-deps

  // Timeline fetch — fires for each newly expanded matchId
  useEffect(() => {
    if (expandedMatchIds.size === 0) return;

    const cleanups: (() => void)[] = [];

    for (const matchId of expandedMatchIds) {
      if (fetchedTimelineMatchIds.current.has(matchId)) continue;
      const detail = matchDetails[matchId];
      if (!detail?.info?.participants) continue;

      const m = matches.find((x) => getMatchId(x) === matchId);
      const participant = m ? getParticipantForMatch(m) : null;
      const participantId = participant?.participantId;
      if (!participantId) continue;

      fetchedTimelineMatchIds.current.add(matchId);
      let isActive = true;
      cleanups.push(() => { isActive = false; });

      void apiGet<LaneStats>(
        `/matches/${matchId}/timeline-stats?participant_id=${participantId}`
      ).then((data) => {
        if (!isActive) return;
        setLaneStatsByMatchId((prev) => ({...prev, [matchId]: data}));
      }).catch(() => {
        if (!isActive) return;
        setLaneStatsByMatchId((prev) => ({...prev, [matchId]: null}));
      });
    }

    return () => {
      for (const cleanup of cleanups) cleanup();
    };
  }, [expandedMatchIds, matchDetails]); // eslint-disable-line react-hooks/exhaustive-deps

  return {championById, rankByPuuid, laneStatsByMatchId};
}
