"use client";

import {useState, useCallback} from "react";

export function useMatchSelection() {
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null);

  const toggleMatch = useCallback((matchId: string) => {
    setSelectedMatchId((prev) => (prev === matchId ? null : matchId));
  }, []);

  const closeMatch = useCallback((matchId: string) => {
    setSelectedMatchId((prev) => (prev === matchId ? null : prev));
  }, []);

  const clearAll = useCallback(() => setSelectedMatchId(null), []);

  return {selectedMatchId, toggleMatch, closeMatch, clearAll};
}
