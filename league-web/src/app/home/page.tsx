"use client";

import {useCallback, useEffect, useMemo, useState} from "react";
import {useRouter} from "next/navigation";
import styles from "./page.module.css";
import MatchPageShell from "../../components/MatchPageShell/MatchPageShell";
import SubHeader from "../../components/SubHeader/SubHeader";
import MatchesTable from "../../components/MatchesTable";
import {apiGet} from "../../lib/api";
import {loadSessionUser} from "../../lib/session";
import {
  getUserDisplayName,
  getRiotAccountId,
  getUserPuuid,
} from "../../lib/user-utils";
import {useLiveGameWhenReady} from "../../lib/hooks/useLiveGameWhenReady";
import {useMatchList} from "../../lib/hooks/useMatchList";
import {LiveGameSlot} from "../../components/LiveGameSlot";
import type {RankInfo} from "../../lib/types/rank";
import type {UserSession} from "../../lib/types/user";

export default function HomePage() {
  const router = useRouter();
  const [user] = useState<UserSession | null>(
    () => loadSessionUser()
  );
  const [rank, setRank] = useState<RankInfo | null>(null);

  const riotAccountId = useMemo(
    () => getRiotAccountId(user),
    [user]
  );
  const displayName = useMemo(
    () => getUserDisplayName(user),
    [user]
  );
  const userPuuid = useMemo(() => getUserPuuid(user), [user]);

  const matchesUrl = useCallback(
    (page: number) =>
      `/riot-accounts/${riotAccountId}/matches?page=${page}&limit=20`,
    [riotAccountId]
  );

  const {
    matches,
    matchDetails,
    isLoading,
    isLoadingMore,
    canLoadMore,
    paginationMeta,
    errorMessage,
    handlePageChange,
    handleRefresh,
    loadMoreMatches,
    refreshIndex,
  } = useMatchList({
    matchesUrl,
    errorScope: "home.overview",
    enabled: !!riotAccountId,
    cacheOptions: {cacheTtlMs: 60_000},
    logTag: "home",
  });

  const {liveGame, status, retry} = useLiveGameWhenReady(
    userPuuid,
    !isLoading
  );

  useEffect(() => {
    if (!user) {
      console.debug("[home] missing session, redirecting");
      router.push("/");
    }
  }, [router, user]);

  // Fetch rank alongside matches (keyed on same triggers)
  useEffect(() => {
    if (!riotAccountId) return;
    let isActive = true;

    const loadRank = async () => {
      console.debug("[home] fetching rank", {riotAccountId});
      try {
        const rankResponse = await apiGet<RankInfo>(
          `/riot-accounts/${riotAccountId}/fetch_rank`,
          {cacheTtlMs: 60_000}
        );
        if (!isActive) return;
        setRank(rankResponse ?? null);
      } catch (err) {
        console.debug("[home] rank fetch failed", {err});
      }
    };

    void loadRank();
    return () => {
      isActive = false;
    };
  }, [riotAccountId, refreshIndex]);

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
        <LiveGameSlot
          status={status}
          liveGame={liveGame}
          targetPuuid={userPuuid}
          onRetry={retry}
        />
      }
      error={errorMessage}
    >
      <MatchesTable
        matches={matches}
        matchDetails={matchDetails}
        user={user}
        targetPuuid={userPuuid}
        isLoading={isLoading}
        isLoadingMore={isLoadingMore}
        canLoadMore={canLoadMore}
        onLoadMore={loadMoreMatches}
        paginationMeta={paginationMeta}
        onPageChange={handlePageChange}
      />
    </MatchPageShell>
  );
}
