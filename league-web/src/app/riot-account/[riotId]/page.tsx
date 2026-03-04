"use client";

import {useEffect, useMemo, useState} from "react";
import {useParams, useRouter} from "next/navigation";
import styles from "./page.module.css";
import Header from "../../../components/Header/Header";
import SubHeader from "../../../components/SubHeader/SubHeader";
import SearchBar from "../../../components/SearchBar/SearchBar";
import MatchesTable from "../../../components/MatchesTable";
import CompareButton from "./CompareButton";
import {apiGet} from "../../../lib/api";
import {useAppError} from "../../../lib/errors/error-store";
import {isApiError} from "../../../lib/errors/types";
import {loadSessionUser} from "../../../lib/session";
import {getMatchId} from "../../../lib/match-utils";
import {useLiveGame} from "../../../lib/hooks/useLiveGame";
import {LiveGameCard} from "../../../components/LiveGameCard";
import type {MatchDetail, MatchSummary, PaginatedMatchList, PaginationMeta} from "../../../lib/types/match";
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
  const [pageError, setPageError] = useState<string | null>(null);
  const [hasSession, setHasSession] = useState(false);
  const [page, setPage] = useState(1);
  const [paginationMeta, setPaginationMeta] = useState<PaginationMeta | null>(null);
  const {errorMessage, reportError, clearError} = useAppError("riotAccount.load");

  const accountPuuid = account?.puuid ?? null;
  const {liveGame} = useLiveGame(accountPuuid);
  const displayLabel = account?.riot_id ?? riotId;

  // Check session (optional for search)
  useEffect(() => {
    const session = loadSessionUser();
    setHasSession(!!session);
    console.debug("[riot-account] session checked", {hasSession: !!session});
  }, []);

  // Reset page when searching a new account
  useEffect(() => {
    setPage(1);
  }, [riotId]);

  // Fetch account — only re-runs when riotId changes, never on page change
  useEffect(() => {
    let isActive = true;

    const load = async () => {
      if (decodeError) {
        console.debug("[riot-account] decode error, aborting account fetch");
        setPageError("Invalid Riot ID in URL. Please re-run your search.");
        clearError();
        return;
      }
      const encodedQuery = encodeURIComponent(riotId);
      console.debug("[riot-account] fetching account", {riotId});
      try {
        const accountResponse = await apiGet<RiotAccountData>(
          `/search/${encodedQuery}/account`,
          {useCache: false}
        );
        if (!isActive) return;
        if (!accountResponse?.puuid) {
          throw new Error("Account not found. Please check the Riot ID and try again.");
        }
        setAccount(accountResponse);
        console.debug("[riot-account] account loaded", {riotId: accountResponse.riot_id});
      } catch (err) {
        if (!isActive) return;
        console.debug("[riot-account] account fetch failed", {err});
        if (isApiError(err) && err.detail === "riot_api_failed" && err.riotStatus === 404) {
          setPageError(`No search results for the summoner "${riotId}".`);
          clearError();
        } else {
          reportError(err);
        }
      }
    };

    void load();
    return () => {
      isActive = false;
    };
  }, [riotId, decodeError, clearError, reportError]);

  // Fetch matches — re-runs on riotId or page change, but never touches the account endpoint
  useEffect(() => {
    let isActive = true;

    const load = async () => {
      if (decodeError) {
        setIsLoading(false);
        return;
      }
      setIsLoading(true);
      setPageError(null);
      clearError();
      const encodedQuery = encodeURIComponent(riotId);
      console.debug("[riot-account] fetching matches", {riotId, page});
      try {
        const matchesResponse = await apiGet<PaginatedMatchList>(
          `/search/${encodedQuery}/matches?page=${page}&limit=20`,
          {useCache: false}
        );
        if (!isActive) return;
        setMatches(Array.isArray(matchesResponse?.data) ? matchesResponse.data : []);
        setPaginationMeta(matchesResponse?.meta ?? null);
        console.debug("[riot-account] matches loaded", {
          matchCount: matchesResponse?.data?.length ?? 0,
        });
      } catch (err) {
        console.debug("[riot-account] matches fetch failed", {err});
        if (isActive) {
          if (isApiError(err) && err.detail === "riot_api_failed" && err.riotStatus === 404) {
            setPageError(`No search results for the summoner "${riotId}".`);
            clearError();
          } else {
            reportError(err);
          }
        }
      } finally {
        if (isActive) setIsLoading(false);
      }
    };

    void load();
    return () => {
      isActive = false;
    };
  }, [riotId, decodeError, page, clearError, reportError]);

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

  const hasMatches = matches.length > 0;
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
        const fresh = await apiGet<PaginatedMatchList>(
          `/search/${encodedQuery}/matches?page=${page}&limit=20`,
          {useCache: false}
        );
        if (!isActive) return;

        const freshArray = Array.isArray(fresh?.data) ? fresh.data : [];
        const stillMissing = freshArray.some((m) => !m.game_info?.info);

        setMatches(freshArray);
        setPaginationMeta(fresh?.meta ?? null);

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
  }, [riotId, page, hasMatches, missingDetailCount, isLoading]);

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    setMatchDetails({});
    window.scrollTo(0, 0);
  };

  const error = pageError ?? errorMessage;

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

      {liveGame && accountPuuid ? (
        <LiveGameCard
          game={liveGame}
          targetPuuid={accountPuuid}
        />
      ) : null}

      {error ? <p className={styles.error}>{error}</p> : null}

      <MatchesTable
        matches={matches}
        matchDetails={matchDetails}
        user={null}
        isSearchView
        targetPuuid={accountPuuid}
        isLoading={isLoading}
        paginationMeta={paginationMeta}
        onPageChange={handlePageChange}
      />
    </div>
  );
}
