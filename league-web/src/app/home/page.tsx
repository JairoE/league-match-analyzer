"use client";

import {useEffect, useMemo, useRef, useState} from "react";
import {useRouter} from "next/navigation";
import styles from "./page.module.css";
import MatchPageShell from "../../components/MatchPageShell/MatchPageShell";
import SubHeader from "../../components/SubHeader/SubHeader";
import MatchesTable from "../../components/MatchesTable";
import {apiGet} from "../../lib/api";
import {clearCache} from "../../lib/cache";
import {useAppError} from "../../lib/errors/error-store";
import {loadSessionUser} from "../../lib/session";
import {
  getUserDisplayName,
  getRiotAccountId,
  getUserPuuid,
} from "../../lib/user-utils";
import {getMatchId} from "../../lib/match-utils";
import {useLiveGame} from "../../lib/hooks/useLiveGame";
import {LiveGameCard} from "../../components/LiveGameCard";
import type {MatchDetail, MatchSummary, PaginatedMatchList, PaginationMeta} from "../../lib/types/match";
import type {RankInfo} from "../../lib/types/rank";
import type {UserSession} from "../../lib/types/user";

export default function HomePage() {
  const router = useRouter();
  const [user] = useState<UserSession | null>(() => loadSessionUser());
  const [matches, setMatches] = useState<MatchSummary[]>([]);
  const [matchDetails, setMatchDetails] = useState<Record<string, MatchDetail>>(
    {}
  );
  const [rank, setRank] = useState<RankInfo | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [refreshIndex, setRefreshIndex] = useState(0);
  const [page, setPage] = useState(1);
  const [paginationMeta, setPaginationMeta] = useState<PaginationMeta | null>(null);
  const {errorMessage, reportError, clearError} = useAppError("home.overview");

  const riotAccountId = useMemo(() => getRiotAccountId(user), [user]);
  const displayName = useMemo(() => getUserDisplayName(user), [user]);
  const userPuuid = useMemo(() => getUserPuuid(user), [user]);
  const {liveGame} = useLiveGame(userPuuid);

  const hasMatches = matches.length > 0;
  const missingDetailCount = useMemo(
    () => matches.filter((m) => !m.game_info?.info).length,
    [matches]
  );
  const pollCountRef = useRef(0);

  useEffect(() => {
    if (!user) {
      console.debug("[home] missing session, redirecting");
      router.push("/");
    }
  }, [router, user]);

  // Load own matches + rank
  useEffect(() => {
    if (!riotAccountId) return;
    let isActive = true;

    const loadOverview = async () => {
      try {
        setIsLoading(true);
        clearError();
        console.debug("[home] fetching matches + rank", {riotAccountId, page});
        const [matchesResponse, rankResponse] = await Promise.all([
          apiGet<PaginatedMatchList>(`/riot-accounts/${riotAccountId}/matches?page=${page}&limit=20`, {
            cacheTtlMs: 60_000,
          }),
          apiGet<RankInfo>(`/riot-accounts/${riotAccountId}/fetch_rank`, {
            cacheTtlMs: 60_000,
          }),
        ]);

        if (!isActive) return;
        const nextMatches = Array.isArray(matchesResponse?.data)
          ? matchesResponse.data
          : [];
        setMatches(nextMatches);
        setPaginationMeta(matchesResponse?.meta ?? null);
        setRank(rankResponse ?? null);
        console.debug("[home] overview loaded", {
          matchCount: nextMatches.length,
        });
      } catch (err) {
        console.debug("[home] overview failed", {err});
        if (isActive) {
          reportError(err);
        }
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    };

    void loadOverview();

    return () => {
      isActive = false;
    };
  }, [riotAccountId, refreshIndex, page, clearError, reportError]);

  // Seed matchDetails from game_info present in the list response.
  useEffect(() => {
    if (!matches.length) {
      setMatchDetails({});
      return;
    }
    const seeded: Record<string, MatchDetail> = {};
    for (const match of matches) {
      const matchId = getMatchId(match);
      if (matchId && match.game_info?.info) {
        seeded[matchId] = match.game_info;
      }
    }
    if (Object.keys(seeded).length > 0) {
      setMatchDetails((prev) => ({...prev, ...seeded}));
    }
  }, [matches]);

  // Reset poll counter on refresh or page change.
  useEffect(() => {
    pollCountRef.current = 0;
  }, [refreshIndex, page]);

  // Poll the match list until all game_info fields are populated.
  useEffect(() => {
    if (!riotAccountId || !hasMatches) return;
    if (missingDetailCount === 0) {
      console.debug("[home] all match details present, no polling needed");
      return;
    }

    let isActive = true;
    const MAX_POLLS = 20;
    const POLL_INTERVAL_MS = 3_000;

    console.debug("[home] starting detail polling", {
      missing: missingDetailCount,
    });

    const poll = setInterval(async () => {
      if (!isActive) return;
      pollCountRef.current++;

      if (pollCountRef.current >= MAX_POLLS) {
        console.debug("[home] polling max reached, stopping");
        clearInterval(poll);
        return;
      }

      try {
        const fresh = await apiGet<PaginatedMatchList>(
          `/riot-accounts/${riotAccountId}/matches?page=${page}&limit=20`,
          {useCache: false}
        );
        if (!isActive) return;

        const freshArray = Array.isArray(fresh?.data) ? fresh.data : [];
        const stillMissing = freshArray.some((m) => !m.game_info?.info);

        setMatches(freshArray);
        setPaginationMeta(fresh?.meta ?? null);

        if (!stillMissing) {
          console.debug("[home] all details populated, stopping poll");
          clearInterval(poll);
        } else {
          console.debug("[home] poll incomplete", {
            poll: pollCountRef.current,
            stillMissing: freshArray.filter((m) => !m.game_info?.info).length,
          });
        }
      } catch (err) {
        console.debug("[home] poll error", {err, poll: pollCountRef.current});
      }
    }, POLL_INTERVAL_MS);

    return () => {
      isActive = false;
      clearInterval(poll);
    };
  }, [riotAccountId, refreshIndex, page, hasMatches, missingDetailCount]);

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    setMatchDetails({});
    window.scrollTo(0, 0);
  };

  const handleRefresh = () => {
    console.debug("[home] manual refresh");
    clearCache();
    setPage(1);
    setRefreshIndex((prev) => prev + 1);
  };

  const rankSubtitle = rank
    ? `${rank.queueType ?? "Ranked"} · ${rank.tier ?? "Unranked"} ${rank.rank ?? ""} · ${rank.leaguePoints ?? 0} LP`
    : "Rank data unavailable";

  if (!user) {
    return <div className={styles.loading}>Redirecting...</div>;
  }

  return (
    <MatchPageShell
      subHeader={
        <SubHeader
          kicker="Signed in as"
          title={displayName}
          subtitle={rankSubtitle}
          actions={
            <button
              className={styles.secondaryButton}
              onClick={handleRefresh}
            >
              Refresh
            </button>
          }
        />
      }
      liveGame={
        liveGame && userPuuid ? (
          <LiveGameCard
            game={liveGame}
            targetPuuid={userPuuid}
          />
        ) : null
      }
      error={errorMessage}
    >
      <MatchesTable
        matches={matches}
        matchDetails={matchDetails}
        user={user}
        targetPuuid={userPuuid}
        isLoading={isLoading}
        paginationMeta={paginationMeta}
        onPageChange={handlePageChange}
      />
    </MatchPageShell>
  );
}
