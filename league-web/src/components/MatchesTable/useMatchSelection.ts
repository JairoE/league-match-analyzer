"use client";

import {useState, useCallback} from "react";

export function useMatchSelection() {
  const [expandedMatchIds, setExpandedMatchIds] = useState<Set<string>>(new Set());

  const toggleMatch = useCallback((matchId: string) => {
    setExpandedMatchIds((prev) => {
      const next = new Set(prev);
      if (next.has(matchId)) {
        next.delete(matchId);
      } else {
        next.add(matchId);
      }
      return next;
    });
  }, []);

  const closeMatch = useCallback((matchId: string) => {
    setExpandedMatchIds((prev) => {
      if (!prev.has(matchId)) return prev;
      const next = new Set(prev);
      next.delete(matchId);
      return next;
    });
  }, []);

  const clearAll = useCallback(() => setExpandedMatchIds(new Set()), []);

  return {expandedMatchIds, toggleMatch, closeMatch, clearAll};
}
