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

  // Champion fetch — missingIds computed inside the functional updater so it reads
  // the latest championById rather than the stale closure value.
  useEffect(() => {
    let isActive = true;

    void Promise.allSettled(
      championIdsToLoad.map(async (id) => {
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
          if (prev[id] == null) next[id] = champion; // skip if already cached
        }
        return Object.keys(next).length === Object.keys(prev).length ? prev : next;
      });
    });

    return () => {
      isActive = false;
    };
  }, [championIdsToLoad]);

  // Rank fetch — triggered by selectedMatchId; functional updater avoids stale rankByPuuid
  useEffect(() => {
    if (!selectedMatchId) return;
    const detail = matchDetails[selectedMatchId];
    if (!detail?.info?.participants) return;

    const missing = detail.info.participants
      .map((p) => p.puuid)
      .filter((puuid): puuid is string => !!puuid && rankByPuuid[puuid] === undefined);

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

  // Timeline fetch — triggered by selectedMatchId
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
