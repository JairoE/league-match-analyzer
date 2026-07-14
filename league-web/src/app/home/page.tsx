"use client";

import {useCallback, useEffect, useMemo, useState} from "react";
import {useRouter} from "next/navigation";
import styles from "./page.module.css";
import MatchPageShell from "../../components/MatchPageShell/MatchPageShell";
import SubHeader from "../../components/SubHeader/SubHeader";
import MatchesTable from "../../components/MatchesTable";
import AnalysisButton from "../../components/AnalysisButton/AnalysisButton";
import AnalysisPanel from "../../components/AnalysisPanel/AnalysisPanel";
import ChatButton from "../../components/ChatPanel/ChatButton";
import ChatPanel from "../../components/ChatPanel/ChatPanel";
import {isDemoMode} from "../../lib/mock/resolve-mock";
import {loadSessionUser} from "../../lib/session";
import {
  getUserDisplayName,
  getRiotAccountId,
  getUserPuuid,
} from "../../lib/user-utils";
import {useAiCoach} from "../../lib/hooks/useAiCoach";
import {useChat} from "../../lib/hooks/useChat";
import {useLiveGameWhenReady} from "../../lib/hooks/useLiveGameWhenReady";
import {useMatchList} from "../../lib/hooks/useMatchList";
import {useRank} from "../../lib/hooks/useRank";
import {LiveGameSlot} from "../../components/LiveGameSlot";
import type {UserSession} from "../../lib/types/user";

export default function HomePage() {
  const router = useRouter();
  const [user] = useState<UserSession | null>(() => loadSessionUser());

  const riotAccountId = useMemo(() => getRiotAccountId(user), [user]);
  const displayName = useMemo(() => getUserDisplayName(user), [user]);
  const userPuuid = useMemo(() => getUserPuuid(user), [user]);

  const currentYear = new Date().getFullYear();

  const matchesUrl = useCallback(
    (page: number, opts?: {refresh?: boolean}) =>
      `/riot-accounts/${riotAccountId}/matches?page=${page}&limit=20&year=${currentYear}${
        opts?.refresh ? "&refresh=true" : ""
      }`,
    [riotAccountId, currentYear]
  );

  const {
    matches,
    matchDetails,
    isLoading,
    isLoadingMore,
    isPending,
    canLoadMore,
    paginationMeta,
    errorMessage,
    staleMessage,
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

  const {liveGame, status, retry, liveGameWarning} = useLiveGameWhenReady(
    userPuuid,
    !isLoading
  );

  const {rank, rankSubtitle, rankStaleMessage} = useRank(
    riotAccountId ?? null,
    {
      refreshIndex,
    }
  );

  const {
    playedChampions,
    selectedChampion,
    selectChampion,
    analysis,
    analysisError,
    isAnalyzing,
    isAnalysisOpen,
    handleAnalysisClick,
    dismissAnalysis,
  } = useAiCoach({
    riotAccountId: riotAccountId ?? null,
    matchDetails,
    puuid: userPuuid,
    rankTier: rank?.tier ?? null,
  });

  const [isChatOpen, setIsChatOpen] = useState(false);
  const {
    messages: chatMessages,
    isStreaming: isChatStreaming,
    toolActivity: chatToolActivity,
    error: chatError,
    sendMessage: sendChatMessage,
  } = useChat(riotAccountId ?? null, {
    championFocus: selectedChampion?.championName ?? null,
  });

  useEffect(() => {
    if (!user) {
      console.debug("[home] missing session, redirecting");
      router.push("/");
    }
  }, [router, user]);

  if (!user) {
    return <div className={styles.loading}>Redirecting...</div>;
  }

  const warning = staleMessage ?? rankStaleMessage ?? liveGameWarning ?? null;

  return (
    <>
      <MatchPageShell
        subHeader={
          <SubHeader
            kicker="Signed in as"
            title={displayName}
            subtitle={rankSubtitle}
            actions={
              <>
                <button
                  className={styles.secondaryButton}
                  onClick={handleRefresh}
                >
                  Refresh
                </button>
                {!isDemoMode() ? (
                  <>
                    <AnalysisButton
                      champions={playedChampions}
                      selectedChampionId={
                        selectedChampion?.championId ?? null
                      }
                      onSelectChampion={selectChampion}
                      isLoading={isAnalyzing}
                      isPanelOpen={isAnalysisOpen}
                      disabled={!riotAccountId || !selectedChampion}
                      onClick={handleAnalysisClick}
                    />
                    <ChatButton
                      isOpen={isChatOpen}
                      disabled={!riotAccountId}
                      onClick={() => setIsChatOpen((open) => !open)}
                    />
                  </>
                ) : null}
              </>
            }
          />
        }
        analysisPanel={
          <AnalysisPanel
            analysis={analysis}
            error={analysisError}
            onDismiss={dismissAnalysis}
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
        warning={warning}
      >
        <MatchesTable
          matches={matches}
          matchDetails={matchDetails}
          user={user}
          targetPuuid={userPuuid}
          isLoading={isLoading}
          isLoadingMore={isLoadingMore}
          isPending={isPending}
          canLoadMore={canLoadMore}
          onLoadMore={loadMoreMatches}
          paginationMeta={paginationMeta}
          onPageChange={handlePageChange}
        />
      </MatchPageShell>
      <ChatPanel
        isOpen={isChatOpen}
        onClose={() => setIsChatOpen(false)}
        messages={chatMessages}
        isStreaming={isChatStreaming}
        toolActivity={chatToolActivity}
        error={chatError}
        onSend={sendChatMessage}
      />
    </>
  );
}
