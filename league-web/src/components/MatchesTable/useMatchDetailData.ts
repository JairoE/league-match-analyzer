"use client";

import {useState, useEffect, useRef} from "react";
import {apiGet} from "../../lib/api";
import {getMatchId} from "../../lib/match-utils";
import type {Champion} from "../../lib/types/champion";
import type {LaneStats, MatchDetail, MatchSummary, Participant} from "../../lib/types/match";
import type {RankBatchResponse, RankInfo} from "../../lib/types/rank";

type UseMatchDetailDataParams = {
  selectedMatchId: string | null;
  matches: MatchSummary[];
  matchDetails: Record<string, MatchDetail>;
  getParticipantForMatch: (match: MatchSummary) => Participant | null;
  championIdsToLoad: number[];
};

export function useMatchDetailData({
  selectedMatchId,
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
        const toAdd = loaded.filter(({id}) => prev[id] == null);
        if (toAdd.length === 0) return prev;
        const next = {...prev};
        for (const {id, champion} of toAdd) next[id] = champion;
        return next;
      });
    });

    return () => {
      isActive = false;
    };
  }, [championIdsToLoad]); // eslint-disable-line react-hooks/exhaustive-deps

  // Rank fetch — fires when a new matchId is selected
  useEffect(() => {
    if (!selectedMatchId) return;
    if (fetchedRankMatchIds.current.has(selectedMatchId)) return;

    const detail = matchDetails[selectedMatchId];
    if (!detail?.info?.participants) return;

    const missing = detail.info.participants
      .map((p) => p.puuid)
      .filter((puuid): puuid is string => !!puuid && rankByPuuid[puuid] === undefined);

    fetchedRankMatchIds.current.add(selectedMatchId);
    if (missing.length === 0) return;

    let isActive = true;

    void apiGet<RankBatchResponse>(`/rank/batch?puuids=${missing.join(",")}`, {
      cacheTtlMs: 3_600_000,
    }).then((data) => {
      if (!isActive) return;
      setRankByPuuid((prev) => ({...prev, ...data}));
    }).catch(() => {/* silently ignore rank errors */});

    return () => {
      isActive = false;
    };
  }, [selectedMatchId, matchDetails]); // eslint-disable-line react-hooks/exhaustive-deps

  // Timeline fetch — fires when a new matchId is selected
  useEffect(() => {
    if (!selectedMatchId) return;
    if (fetchedTimelineMatchIds.current.has(selectedMatchId)) return;

    const detail = matchDetails[selectedMatchId];
    if (!detail?.info?.participants) return;

    const m = matches.find((x) => getMatchId(x) === selectedMatchId);
    const participant = m ? getParticipantForMatch(m) : null;
    const participantId = participant?.participantId;
    if (!participantId) return;

    fetchedTimelineMatchIds.current.add(selectedMatchId);
    let isActive = true;

    void apiGet<LaneStats>(
      `/matches/${selectedMatchId}/timeline-stats?participant_id=${participantId}`
    ).then((data) => {
      if (!isActive) return;
      setLaneStatsByMatchId((prev) => ({...prev, [selectedMatchId]: data}));
    }).catch(() => {
      if (!isActive) return;
      setLaneStatsByMatchId((prev) => ({...prev, [selectedMatchId]: null}));
    });

    return () => {
      isActive = false;
    };
  }, [selectedMatchId, matchDetails]); // eslint-disable-line react-hooks/exhaustive-deps

  return {championById, rankByPuuid, laneStatsByMatchId};
}
