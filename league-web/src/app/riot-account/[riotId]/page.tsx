"use client";

import {useEffect, useMemo, useState} from "react";
import {useParams, useRouter} from "next/navigation";
import styles from "./page.module.css";
import Header from "../../../components/Header";
import SubHeader from "../../../components/SubHeader";
import SearchBar from "../../../components/SearchBar";
import MatchCard from "../../../components/MatchCard";
import CompareButton from "./CompareButton";
import {apiGet} from "../../../lib/api";
import {loadSessionUser} from "../../../lib/session";
import {getMatchId} from "../../../lib/match-utils";
import type {MatchDetail, MatchSummary} from "../../../lib/types/match";
import type {RiotAccountData} from "../../../lib/types/user";

export default function RiotAccountPage() {
  const params = useParams<{riotId: string}>();
  const router = useRouter();
  const {riotId, decodeError} = useMemo(() => {
    try {
      return {riotId: decodeURIComponent(params.riotId), decodeError: false};
    } catch (error) {
      console.debug("[riot-account] invalid riotId encoding", {
        raw: params.riotId,
        error,
      });
      return {riotId: params.riotId, decodeError: true};
    }
  }, [params.riotId]);

  const [account, setAccount] = useState<RiotAccountData | null>(null);
  const [matches, setMatches] = useState<MatchSummary[]>([]);
  const [matchDetails, setMatchDetails] = useState<Record<string, MatchDetail>>(
    {}
  );
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasSession, setHasSession] = useState(false);

  const accountPuuid = account?.puuid ?? null;
  const displayLabel = account?.riot_id ?? riotId;

  // Check session (optional for search)
  useEffect(() => {
    const session = loadSessionUser();
    setHasSession(!!session);
    console.debug("[riot-account] session checked", {hasSession: !!session});
  }, []);

  // Fetch searched account data + matches
  useEffect(() => {
    let isActive = true;

    const load = async () => {
      try {
        if (decodeError) {
          console.debug("[riot-account] decode error, aborting fetch");
          setError("Invalid Riot ID in URL. Please re-run your search.");
          setIsLoading(false);
          return;
        }
        setIsLoading(true);
        setError(null);
        const encodedQuery = encodeURIComponent(riotId);
        console.debug("[riot-account] fetching", {riotId});

        const [matchesResponse, accountResponse] = await Promise.all([
          apiGet<MatchSummary[]>(`/search/${encodedQuery}/matches`, {
            useCache: false,
          }),
          apiGet<RiotAccountData>(`/search/${encodedQuery}/account`, {
            useCache: false,
          }),
        ]);

        if (!isActive) return;

        if (!accountResponse?.puuid) {
          throw new Error("Account not found or missing PUUID");
        }

        setAccount(accountResponse);
        setMatches(Array.isArray(matchesResponse) ? matchesResponse : []);
        console.debug("[riot-account] loaded", {
          riotId: accountResponse.riot_id,
          matchCount: Array.isArray(matchesResponse)
            ? matchesResponse.length
            : 0,
        });
      } catch (err) {
        console.debug("[riot-account] load failed", {err});
        if (isActive) {
          setError("Failed to load account. Check the Riot ID and try again.");
        }
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    };

    void load();

    return () => {
      isActive = false;
    };
  }, [riotId, decodeError]);

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

  const hasMatches = useMemo(() => matches.length > 0, [matches]);
  const missingDetailCount = useMemo(
    () => matches.filter((m) => !m.game_info?.info).length,
    [matches]
  );

  // Poll until all game_info fields are populated.
  useEffect(() => {
    if (!hasMatches || isLoading) return;
    if (missingDetailCount === 0) {
      console.debug(
        "[riot-account] all match details present, no polling needed"
      );
      return;
    }

    let isActive = true;
    let pollCount = 0;
    const MAX_POLLS = 20;
    const POLL_INTERVAL_MS = 3_000;
    const encodedQuery = encodeURIComponent(riotId);

    console.debug("[riot-account] starting detail polling", {
      missing: missingDetailCount,
    });

    const poll = setInterval(async () => {
      if (!isActive) return;
      pollCount++;

      if (pollCount >= MAX_POLLS) {
        console.debug("[riot-account] polling max reached, stopping");
        clearInterval(poll);
        return;
      }

      try {
        const fresh = await apiGet<MatchSummary[]>(
          `/search/${encodedQuery}/matches`,
          {useCache: false}
        );
        if (!isActive) return;

        const freshArray = Array.isArray(fresh) ? fresh : [];
        const stillMissing = freshArray.some((m) => !m.game_info?.info);

        setMatches(freshArray);

        if (!stillMissing) {
          console.debug("[riot-account] all details populated, stopping poll");
          clearInterval(poll);
        } else {
          console.debug("[riot-account] poll incomplete", {
            poll: pollCount,
            stillMissing: freshArray.filter((m) => !m.game_info?.info).length,
          });
        }
      } catch (err) {
        console.debug("[riot-account] poll error", {err, poll: pollCount});
      }
    }, POLL_INTERVAL_MS);

    return () => {
      isActive = false;
      clearInterval(poll);
    };
  }, [riotId, hasMatches, missingDetailCount, isLoading]);

  return (
    <div className={styles.page}>
      <Header />

      <SubHeader
        kicker="Viewing matches for"
        title={displayLabel}
        actions={
          <>
            {hasSession ? (
              <button
                className={styles.secondaryButton}
                onClick={() => router.push("/home")}
              >
                &larr; My matches
              </button>
            ) : null}
            <CompareButton />
          </>
        }
      />

      <SearchBar />

      {error ? <p className={styles.error}>{error}</p> : null}

      {isLoading ? (
        <p className={styles.loadingInline}>Loading matches...</p>
      ) : null}

      {!isLoading && matches.length === 0 ? (
        <p className={styles.empty}>No matches found.</p>
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
                user={null}
                isSearchView
                targetPuuid={accountPuuid}
              />
            );
          })}
        </section>
      )}
    </div>
  );
}
