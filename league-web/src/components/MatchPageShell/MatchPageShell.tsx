"use client";

import type {ReactNode} from "react";
import styles from "./MatchPageShell.module.css";
import Header from "../Header/Header";
import SearchBar from "../SearchBar/SearchBar";

type MatchPageShellProps = {
  subHeader: ReactNode;
  error?: string | null;
  warning?: string | null;
  liveGame?: ReactNode;
  analysisPanel?: ReactNode;
  children: ReactNode;
};

export default function MatchPageShell({
  subHeader,
  error,
  warning,
  liveGame,
  analysisPanel,
  children,
}: MatchPageShellProps) {
  return (
    <div className={styles.page}>
      <Header />
      {subHeader}
      <SearchBar />
      {liveGame}
      {analysisPanel}
      {warning ? <p className={styles.warning}>{warning}</p> : null}
      {error ? <p className={styles.error}>{error}</p> : null}
      {children}
    </div>
  );
}
