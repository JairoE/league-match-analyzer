"use client";

import {useCallback, useEffect, useMemo, useState} from "react";
import {useParams, useRouter} from "next/navigation";
import styles from "./page.module.css";
import MatchPageShell from "../../../components/MatchPageShell/MatchPageShell";
import SubHeader from "../../../components/SubHeader/SubHeader";
import MatchesTable from "../../../components/MatchesTable";
import CompareButton from "./CompareButton";
import {apiGet} from "../../../lib/api";
import {isApiError} from "../../../lib/errors/types";
import {loadSessionUser} from "../../../lib/session";
import {useLiveGameWhenReady} from "../../../lib/hooks/useLiveGameWhenReady";
import {useMatchList} from "../../../lib/hooks/useMatchList";
import {useRank} from "../../../lib/hooks/useRank";
import {LiveGameSlot} from "../../../components/LiveGameSlot";
import type {RiotAccountData} from "../../../lib/types/user";

export default function RiotAccountPage() {
  const params = useParams<{riotId: string}>();
  const router = useRouter();
  const {riotId, decodeError} = useMemo(() => {
    try {
      return {
        riotId: decodeURIComponent(params.riotId),
        decodeError: false,
      };
    } catch (error) {
      console.debug("[riot-account] invalid riotId encoding", {
        raw: params.riotId,
        error,
      });
      return {riotId: params.riotId, decodeError: true};
    }
  }, [params.riotId]);

  const [account, setAccount] =
    useState<RiotAccountData | null>(null);
  const [pageError, setPageError] = useState<string | null>(
    null
  );
  const [hasSession, setHasSession] = useState(false);

  const accountPuuid = account?.puuid ?? null;
  const displayLabel = account?.riot_id ?? riotId;

  const currentYear = new Date().getFullYear();

  const matchesUrl = useCallback(
    (page: number, opts?: {refresh?: boolean}) => {
      const encoded = encodeURIComponent(riotId);
      return `/search/${encoded}/matches?page=${page}&limit=20&year=${currentYear}${
        opts?.refresh ? "&refresh=true" : ""
      }`;
    },
    [riotId, currentYear]
  );

  const handleMatchFetchError = useCallback(
    (err: unknown): boolean => {
      if (
        isApiError(err) &&
        err.detail === "riot_api_failed" &&
        err.riotStatus === 404
      ) {
        setPageError(
          `No search results for the summoner "${riotId}".`
        );
        return true;
      }
      return false;
    },
    [riotId]
  );

  const {
    matches,
    matchDetails,
    isLoading,
    isLoadingMore,
    canLoadMore,
    paginationMeta,
    errorMessage,
    staleMessage,
    clearError,
    reportError,
    handlePageChange,
    handleRefresh,
    loadMoreMatches,
    refreshIndex,
  } = useMatchList({
    matchesUrl,
    errorScope: "riotAccount.load",
    enabled: !decodeError,
    logTag: "riot-account",
    onFetchError: handleMatchFetchError,
    resetKey: riotId,
  });

  const {liveGame, status, retry, liveGameWarning} = useLiveGameWhenReady(
    accountPuuid,
    !isLoading
  );

  const {rankSubtitle, rankStaleMessage} = useRank(account?.id ?? null, {
    refreshIndex,
  });

  // Check session (optional for search)
  useEffect(() => {
    const session = loadSessionUser();
    setHasSession(!!session);
    console.debug("[riot-account] session checked", {
      hasSession: !!session,
    });
  }, []);

  // Fetch account — only re-runs when riotId changes
  useEffect(() => {
    let isActive = true;

    const load = async () => {
      if (decodeError) {
        console.debug(
          "[riot-account] decode error, aborting account fetch"
        );
        setPageError(
          "Invalid Riot ID in URL. Please re-run your search."
        );
        clearError();
        return;
      }
      const encodedQuery = encodeURIComponent(riotId);
      console.debug("[riot-account] fetching account", {
        riotId,
      });
      try {
        const accountResponse = await apiGet<RiotAccountData>(
          `/search/${encodedQuery}/account`,
          {useCache: false}
        );
        if (!isActive) return;
        if (!accountResponse?.puuid) {
          throw new Error(
            "Account not found. Please check the Riot ID and try again."
          );
        }
        setAccount(accountResponse);
        console.debug("[riot-account] account loaded", {
          riotId: accountResponse.riot_id,
        });
      } catch (err) {
        if (!isActive) return;
        console.debug("[riot-account] account fetch failed", {
          err,
        });
        if (
          isApiError(err) &&
          err.detail === "riot_api_failed" &&
          err.riotStatus === 404
        ) {
          setPageError(
            `No search results for the summoner "${riotId}".`
          );
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
  }, [riotId, decodeError, refreshIndex, clearError, reportError]);

  const error = pageError ?? errorMessage;
  const warning =
    staleMessage ?? rankStaleMessage ?? liveGameWarning ?? null;

  return (
    <MatchPageShell
      subHeader={
        <SubHeader
          kicker="Viewing matches for"
          title={displayLabel}
          subtitle={rankSubtitle}
          actions={
            <>
              <button
                className={styles.secondaryButton}
                onClick={handleRefresh}
              >
                Refresh
              </button>
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
      }
      liveGame={
        <LiveGameSlot
          status={status}
          liveGame={liveGame}
          targetPuuid={accountPuuid}
          onRetry={retry}
        />
      }
      error={error}
      warning={warning}
    >
      <MatchesTable
        matches={matches}
        matchDetails={matchDetails}
        user={null}
        isSearchView
        targetPuuid={accountPuuid}
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
