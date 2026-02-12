"use client";

import {useEffect, useMemo, useState} from "react";
import {useRouter} from "next/navigation";
import styles from "./page.module.css";
import MatchCard from "../../components/MatchCard";
import {apiGet} from "../../lib/api";
import {clearCache} from "../../lib/cache";
import {loadSessionUser, clearSessionUser} from "../../lib/session";
import {
  getUserDisplayName,
  getRiotAccountId,
  getUserPuuid,
} from "../../lib/user-utils";
import {getMatchId} from "../../lib/match-utils";
import type {MatchDetail, MatchSummary} from "../../lib/types/match";
import type {RankInfo} from "../../lib/types/rank";
import type {RiotAccountData, UserSession} from "../../lib/types/user";

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

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [searchedAccount, setSearchedAccount] = useState<string | null>(null); // riot_id of searched account
  const [searchedPuuid, setSearchedPuuid] = useState<string | null>(null);

  const riotAccountId = useMemo(() => getRiotAccountId(user), [user]);
  const displayName = useMemo(() => getUserDisplayName(user), [user]);
  const userPuuid = useMemo(() => getUserPuuid(user), [user]);

  // Determine what we're currently viewing
  const isViewingSearch = searchedAccount !== null;
  const viewLabel = isViewingSearch ? searchedAccount : displayName;
  const targetPuuid = isViewingSearch ? searchedPuuid : userPuuid;

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

  // Load own matches + rank
  useEffect(() => {
    if (!riotAccountId || isViewingSearch) return;
    let isActive = true;

    const loadOverview = async () => {
      try {
        setIsLoading(true);
        setError(null);
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
  }, [riotAccountId, refreshIndex, isViewingSearch]);

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
    if (!riotAccountId || !matches.length || isViewingSearch) return;

    const hasMissing = matches.some((m) => !m.game_info?.info);
    if (!hasMissing) {
      console.debug("[home] all match details present, no polling needed");
      return;
    }

    let isActive = true;
    let pollCount = 0;
    const MAX_POLLS = 20;
    const POLL_INTERVAL_MS = 3_000;

    console.debug("[home] starting detail polling", {
      missing: matches.filter((m) => !m.game_info?.info).length,
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [riotAccountId, refreshIndex, isViewingSearch]);

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

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    const query = searchQuery.trim();
    if (!query) return;

    setIsSearching(true);
    setError(null);

    try {
      console.debug("[home] searching", {query});
      // URL-encode the # in riot IDs
      const encodedQuery = encodeURIComponent(query);
      const [searchMatches, accountResponse] = await Promise.all([
        apiGet<MatchSummary[]>(`/search/${encodedQuery}/matches`, {
          useCache: false,
        }),
        apiGet<RiotAccountData>(`/search/${encodedQuery}/account`, {
          useCache: false,
        }),
      ]);

      const resultMatches = Array.isArray(searchMatches) ? searchMatches : [];
      setMatches(resultMatches);
      setSearchedAccount(accountResponse?.riot_id ?? query);
      setSearchedPuuid(accountResponse?.puuid ?? null);
      setRank(null);
      console.debug("[home] search done", {
        count: resultMatches.length,
        riotId: accountResponse?.riot_id ?? query,
        puuid: accountResponse?.puuid ?? null,
      });
    } catch (err) {
      console.debug("[home] search failed", {err});
      setError("Search failed. Check the Riot ID and try again.");
    } finally {
      setIsSearching(false);
    }
  };

  const handleBackToMyMatches = () => {
    console.debug("[home] returning to signed-in matches");
    setSearchedAccount(null);
    setSearchedPuuid(null);
    setSearchQuery("");
    setMatches([]);
    setMatchDetails({});
    setRefreshIndex((prev) => prev + 1);
  };

  if (!isHydrated) {
    return <div className={styles.loading}>Loading session...</div>;
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <p className={styles.kicker}>
            {isViewingSearch ? "Viewing matches for" : "Signed in as"}
          </p>
          <h1>{viewLabel}</h1>
          {!isViewingSearch && rank ? (
            <p className={styles.rank}>
              {rank.queueType ?? "Ranked"} · {rank.tier ?? "Unranked"}{" "}
              {rank.rank ?? ""} · {rank.leaguePoints ?? 0} LP
            </p>
          ) : !isViewingSearch ? (
            <p className={styles.rank}>Rank data unavailable</p>
          ) : null}
        </div>
        <div className={styles.actions}>
          {isViewingSearch ? (
            <button
              className={styles.secondaryButton}
              onClick={handleBackToMyMatches}
            >
              ← My matches
            </button>
          ) : (
            <button className={styles.secondaryButton} onClick={handleRefresh}>
              Refresh
            </button>
          )}
          <button className={styles.primaryButton} onClick={handleSignOut}>
            Sign out
          </button>
        </div>
      </header>

      {/* Search bar */}
      <form className={styles.searchForm} onSubmit={handleSearch}>
        <input
          className={styles.searchInput}
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search summoner (e.g. Name#TAG)"
          disabled={isSearching}
        />
        <button
          className={styles.searchButton}
          type="submit"
          disabled={isSearching || !searchQuery.trim()}
        >
          {isSearching ? "Searching..." : "Search"}
        </button>
      </form>

      {error ? <p className={styles.error}>{error}</p> : null}

      {isLoading || isSearching ? (
        <p className={styles.loadingInline}>
          {isSearching ? "Searching..." : "Loading matches..."}
        </p>
      ) : null}

      {!isLoading && !isSearching && matches.length === 0 ? (
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
                targetPuuid={targetPuuid}
              />
            );
          })}
        </section>
      )}
    </div>
  );
}
