"use client";

import {useEffect, useMemo, useState} from "react";
import {useRouter} from "next/navigation";
import styles from "./page.module.css";
import MatchCard from "../../components/MatchCard";
import {apiGet} from "../../lib/api";
import {clearCache} from "../../lib/cache";
import {loadSessionUser, clearSessionUser} from "../../lib/session";
import {getUserDisplayName, getUserId} from "../../lib/user-utils";
import {getMatchId} from "../../lib/match-utils";
import type {MatchDetail, MatchSummary} from "../../lib/types/match";
import type {RankInfo} from "../../lib/types/rank";
import type {UserSession} from "../../lib/types/user";

export default function HomePage() {
  const router = useRouter();
  const [user, setUser] = useState<UserSession | null>(null);
  const [matches, setMatches] = useState<MatchSummary[]>([]);
  const [matchDetails, setMatchDetails] = useState<Record<string, MatchDetail>>(
    {}
  );
  const [rank, setRank] = useState<RankInfo | null>(null);
  const [isHydrated, setIsHydrated] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshIndex, setRefreshIndex] = useState(0);

  const userId = useMemo(() => getUserId(user), [user]);
  const displayName = useMemo(() => getUserDisplayName(user), [user]);

  useEffect(() => {
    const session = loadSessionUser();
    if (!session) {
      console.debug("[home] missing session, redirecting");
      router.push("/");
      setIsHydrated(true);
      return;
    }
    console.debug("[home] session restored");
    setUser(session);
    setIsHydrated(true);
  }, [router]);

  useEffect(() => {
    if (!userId) return;
    let isActive = true;

    const loadOverview = async () => {
      try {
        setIsLoading(true);
        setError(null);
        console.debug("[home] fetching matches + rank", {userId});
        const [matchesResponse, rankResponse] = await Promise.all([
          apiGet<MatchSummary[]>(`/users/${userId}/matches`, {
            cacheTtlMs: 60_000,
          }),
          apiGet<RankInfo>(`/users/${userId}/fetch_rank`, {cacheTtlMs: 60_000}),
        ]);

        if (!isActive) return;
        const nextMatches = Array.isArray(matchesResponse)
          ? matchesResponse
          : [];
        setMatches(nextMatches);
        setRank(rankResponse ?? null);
        console.debug("[home] overview loaded", {
          matchCount: nextMatches.length,
        });
      } catch (err) {
        console.debug("[home] overview failed", {err});
        if (isActive) {
          setError("Failed to load matches. Please refresh.");
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
  }, [userId, refreshIndex]);

  useEffect(() => {
    if (!matches.length) {
      setMatchDetails({});
      return;
    }
    let isActive = true;
    const matchIds = matches
      .map((match) => getMatchId(match))
      .filter((matchId): matchId is string => Boolean(matchId))
      .slice(0, 20);

    const loadDetails = async () => {
      try {
        console.debug("[home] fetching match details", {
          count: matchIds.length,
        });
        const responses = await Promise.all(
          matchIds.map(async (matchId) => {
            const detail = await apiGet<MatchDetail>(`/matches/${matchId}`, {
              cacheTtlMs: 120_000,
            });
            return [matchId, detail] as const;
          })
        );

        if (!isActive) return;
        const detailMap: Record<string, MatchDetail> = {};
        responses.forEach(([matchId, detail]) => {
          detailMap[matchId] = detail;
        });
        setMatchDetails(detailMap);
        console.debug("[home] match details loaded", {count: responses.length});
      } catch (err) {
        console.debug("[home] match detail failed", {err});
      }
    };

    void loadDetails();

    return () => {
      isActive = false;
    };
  }, [matches, refreshIndex]);

  const handleRefresh = () => {
    console.debug("[home] manual refresh");
    clearCache();
    setRefreshIndex((prev) => prev + 1);
  };

  const handleSignOut = () => {
    console.debug("[home] sign out");
    clearSessionUser();
    router.push("/");
  };

  if (!isHydrated) {
    return <div className={styles.loading}>Loading session...</div>;
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <p className={styles.kicker}>Signed in as</p>
          <h1>{displayName}</h1>
          {rank ? (
            <p className={styles.rank}>
              {rank.queueType ?? "Ranked"} · {rank.tier ?? "Unranked"}{" "}
              {rank.rank ?? ""} · {rank.leaguePoints ?? 0} LP
            </p>
          ) : (
            <p className={styles.rank}>Rank data unavailable</p>
          )}
        </div>
        <div className={styles.actions}>
          <button className={styles.secondaryButton} onClick={handleRefresh}>
            Refresh
          </button>
          <button className={styles.primaryButton} onClick={handleSignOut}>
            Sign out
          </button>
        </div>
      </header>

      {error ? <p className={styles.error}>{error}</p> : null}

      {isLoading ? (
        <p className={styles.loadingInline}>Loading matches...</p>
      ) : null}

      {!isLoading && matches.length === 0 ? (
        <p className={styles.empty}>No matches yet.</p>
      ) : (
        <section className={styles.matches}>
          {matches.map((match, index) => {
            const matchId = getMatchId(match);
            const detail = matchId ? (matchDetails[matchId] ?? null) : null;
            return (
              <MatchCard
                key={matchId ?? `match-${index}`}
                match={match}
                detail={detail}
                user={user}
              />
            );
          })}
        </section>
      )}
    </div>
  );
}
