"use client";

import {useState, useCallback} from "react";

export function useMatchSelection() {
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null);

  const handleRowClick = useCallback((matchId: string) => {
    setSelectedMatchId((prev) => (prev === matchId ? null : matchId));
  }, []);

  const clearSelection = useCallback(() => setSelectedMatchId(null), []);

  return {selectedMatchId, handleRowClick, handleClosePanel: clearSelection, clearSelection};
}
