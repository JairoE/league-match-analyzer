"use client";

import {useEffect, useMemo, useState} from "react";
import {useRouter} from "next/navigation";
import styles from "./page.module.css";
import Header from "../../components/Header";
import SubHeader from "../../components/SubHeader";
import SearchBar from "../../components/SearchBar";
import MatchCard from "../../components/MatchCard";
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
import type {MatchDetail, MatchSummary} from "../../lib/types/match";
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
  const {errorMessage, reportError, clearError} = useAppError("home.overview");

  const riotAccountId = useMemo(() => getRiotAccountId(user), [user]);
  const displayName = useMemo(() => getUserDisplayName(user), [user]);
  const userPuuid = useMemo(() => getUserPuuid(user), [user]);

  const hasMatches = useMemo(() => matches.length > 0, [matches]);
  const missingDetailCount = useMemo(
    () => matches.filter((m) => !m.game_info?.info).length,
    [matches]
  );

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
        console.debug("[home] fetching matches + rank", {riotAccountId});
        const [matchesResponse, rankResponse] = await Promise.all([
          apiGet<MatchSummary[]>(`/riot-accounts/${riotAccountId}/matches`, {
            cacheTtlMs: 60_000,
          }),
          apiGet<RankInfo>(`/riot-accounts/${riotAccountId}/fetch_rank`, {
            cacheTtlMs: 60_000,
          }),
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
  }, [riotAccountId, refreshIndex, clearError, reportError]);

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
  useEffect(() => {
    if (!riotAccountId || !hasMatches) return;
    if (missingDetailCount === 0) {
      console.debug("[home] all match details present, no polling needed");
      return;
    }

    let isActive = true;
    let pollCount = 0;
    const MAX_POLLS = 20;
    const POLL_INTERVAL_MS = 3_000;

    console.debug("[home] starting detail polling", {
      missing: missingDetailCount,
    });

    const poll = setInterval(async () => {
      if (!isActive) return;
      pollCount++;

      if (pollCount >= MAX_POLLS) {
        console.debug("[home] polling max reached, stopping");
        clearInterval(poll);
        return;
      }

      try {
        const fresh = await apiGet<MatchSummary[]>(
          `/riot-accounts/${riotAccountId}/matches`,
          {useCache: false}
        );
        if (!isActive) return;

        const freshArray = Array.isArray(fresh) ? fresh : [];
        const stillMissing = freshArray.some((m) => !m.game_info?.info);

        setMatches(freshArray);

        if (!stillMissing) {
          console.debug("[home] all details populated, stopping poll");
          clearInterval(poll);
        } else {
          console.debug("[home] poll incomplete", {
            poll: pollCount,
            stillMissing: freshArray.filter((m) => !m.game_info?.info).length,
          });
        }
      } catch (err) {
        console.debug("[home] poll error", {err, poll: pollCount});
      }
    }, POLL_INTERVAL_MS);

    return () => {
      isActive = false;
      clearInterval(poll);
    };
  }, [riotAccountId, refreshIndex, hasMatches, missingDetailCount]);

  const handleRefresh = () => {
    console.debug("[home] manual refresh");
    clearCache();
    setRefreshIndex((prev) => prev + 1);
  };

  const rankSubtitle = rank
    ? `${rank.queueType ?? "Ranked"} · ${rank.tier ?? "Unranked"} ${rank.rank ?? ""} · ${rank.leaguePoints ?? 0} LP`
    : "Rank data unavailable";

  if (!user) {
    return <div className={styles.loading}>Redirecting...</div>;
  }

  return (
    <div className={styles.page}>
      <Header />

      <SubHeader
        kicker="Signed in as"
        title={displayName}
        subtitle={rankSubtitle}
        actions={
          <button className={styles.secondaryButton} onClick={handleRefresh}>
            Refresh
          </button>
        }
      />

      <SearchBar />

      {errorMessage ? <p className={styles.error}>{errorMessage}</p> : null}

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
                targetPuuid={userPuuid}
              />
            );
          })}
        </section>
      )}
    </div>
  );
}
