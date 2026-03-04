"use client";

import {useState, useEffect} from "react";
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

type UseMatchDetailDataResult = {
  championById: Record<number, Champion>;
  rankByPuuid: Record<string, RankInfo | null>;
  laneStatsByMatchId: Record<string, LaneStats | null>;
};

export function useMatchDetailData({
  selectedMatchId,
  matches,
  matchDetails,
  getParticipantForMatch,
  championIdsToLoad,
}: UseMatchDetailDataParams): UseMatchDetailDataResult {
  const [championById, setChampionById] = useState<Record<number, Champion>>({});
  const [rankByPuuid, setRankByPuuid] = useState<Record<string, RankInfo | null>>({});
  const [laneStatsByMatchId, setLaneStatsByMatchId] = useState<Record<string, LaneStats | null>>({});

  // Champion fetch — triggered by championIdsToLoad; uses functional updater to avoid stale closure
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
        for (const {id, champion} of loaded) next[id] = champion;
        return next;
      });
    });

    return () => {
      isActive = false;
    };
  }, [championIdsToLoad]); // eslint-disable-line react-hooks/exhaustive-deps
  // championById intentionally omitted — functional updater `prev =>` avoids stale closure

  // Rank fetch — triggered by selectedMatchId; functional updater avoids stale rankByPuuid
  useEffect(() => {
    if (!selectedMatchId) return;
    const detail = matchDetails[selectedMatchId];
    if (!detail?.info?.participants) return;

    const puuids = detail.info.participants
      .map((p) => p.puuid)
      .filter((puuid): puuid is string => !!puuid);

    const missing = puuids.filter((puuid) => rankByPuuid[puuid] === undefined);
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
  // rankByPuuid intentionally omitted — functional updater `prev =>` avoids stale closure

  // Timeline fetch — triggered by selectedMatchId; functional updater used so laneStatsByMatchId
  // is NOT needed as a dep (reading stale value for the cache-hit check is intentional —
  // a re-render will provide a fresh value before this effect fires again).
  useEffect(() => {
    if (!selectedMatchId) return;
    if (laneStatsByMatchId[selectedMatchId] !== undefined) return;

    const detail = matchDetails[selectedMatchId];
    if (!detail?.info?.participants) return;

    const m = matches.find((x) => getMatchId(x) === selectedMatchId);
    const participant = m ? getParticipantForMatch(m) : null;
    const participantId = participant?.participantId;
    if (!participantId) return;

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
  // matches, getParticipantForMatch, laneStatsByMatchId intentionally omitted:
  // selectedMatchId/matchDetails changing is the correct trigger; participant lookup is stable
  // within a selection; functional updater `prev =>` avoids stale laneStatsByMatchId reads.

  return {championById, rankByPuuid, laneStatsByMatchId};
}
