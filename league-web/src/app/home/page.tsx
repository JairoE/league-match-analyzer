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
  const hasMatches = useMemo(() => matches.length > 0, [matches]);
  const shouldPollDetails = useMemo(() => {
    if (!userId || !matches.length) return false;
    return matches.some((m) => !m.game_info?.info);
  }, [matches, userId]);

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

  // Poll the match list until all game_info fields are populated.
  // The backend enqueues ARQ detail-fetch jobs on each list request,
  // so polling picks up newly populated details as the worker fills them in.
  useEffect(() => {
    if (!userId || !shouldPollDetails) {
      if (userId && hasMatches) {
        console.debug("[home] all match details present, no polling needed");
      }
      return;
    }

    let isActive = true;
    let pollCount = 0;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    const MAX_POLLS = 20;
    const POLL_INTERVAL_MS = 3_000;

    console.debug("[home] starting detail polling");

    const pollOnce = async () => {
      if (!isActive) return;

      // pollCount tracks *actual fetch attempts made*.
      // Guard before increment so MAX_POLLS means "max API calls".
      if (pollCount >= MAX_POLLS) {
        console.debug("[home] polling max reached, stopping", {
          max: MAX_POLLS,
          attempts: pollCount,
        });
        return;
      }
      pollCount++;
      const attempt = pollCount;

      try {
        const fresh = await apiGet<MatchSummary[]>(`/users/${userId}/matches`, {
          useCache: false,
        });
        if (!isActive) return;

        const freshArray = Array.isArray(fresh) ? fresh : [];
        const stillMissing = freshArray.some((m) => !m.game_info?.info);

        setMatches(freshArray);

        if (!stillMissing) {
          console.debug("[home] all details populated, stopping poll");
          return;
        }

        console.debug("[home] poll incomplete", {
          poll: attempt,
          stillMissing: freshArray.filter((m) => !m.game_info?.info).length,
        });
      } catch (err) {
        console.debug("[home] poll error", {err, poll: attempt});
      }

      if (!isActive) return;
      if (pollCount >= MAX_POLLS) {
        console.debug("[home] polling max reached after attempt, stopping", {
          max: MAX_POLLS,
          attempts: pollCount,
        });
        return;
      }
      timeoutId = setTimeout(() => {
        void pollOnce();
      }, POLL_INTERVAL_MS);
    };

    void pollOnce();

    return () => {
      isActive = false;
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, refreshIndex, shouldPollDetails, hasMatches]);

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
            const detail = matchId ? matchDetails[matchId] ?? null : null;
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
